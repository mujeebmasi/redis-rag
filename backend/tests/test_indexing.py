"""
Indexing pipeline tests: SHA cache, expiry, pruning, and the background job.
"""

import json

import pytest

import app.api.github as github_api
import app.services.embedding_service as svc
from app.core.indexing_config import DATA_TTL_SECONDS, EMBEDDING_DIM
from app.services.github_service import GitHubError


class FakeEmbedder:
    """Stands in for Gemini; counts how many texts it embedded."""

    def __init__(self):
        self.embedded = 0
        self.pause_seconds = None  # Set to act as if Gemini's rate limit was hit

    def embed_documents(self, texts, on_rate_limit=None):
        if self.pause_seconds and on_rate_limit:
            on_rate_limit(self.pause_seconds)
        self.embedded += len(texts)
        return [[0.1] * EMBEDDING_DIM for _ in texts]


@pytest.fixture
def embedder(fake_redis, monkeypatch):
    fake = FakeEmbedder()
    monkeypatch.setattr(svc, "_get_embeddings_model", lambda: fake)
    # fakeredis has no FT.CREATE; the index itself is tested against real Redis
    monkeypatch.setattr(svc, "_create_index_if_not_exists", lambda: None)
    return fake


def _repo(name, sha, text=None):
    return {"name": name, "readme": text or f"# {name}\n" + "Some README text. " * 30, "readme_sha": sha}


def _doc_keys(redis, user):
    return sorted(redis.scan_iter(match=f"doc:readme:{user}:*"))


def test_first_run_embeds_and_sets_expiry(embedder, fake_redis):
    stats = svc.embed_and_store("alice", [_repo("app", "sha1"), _repo("lib", "sha2")])

    assert stats["repos_embedded"] == 2
    keys = _doc_keys(fake_redis, "alice")
    assert keys == ["doc:readme:alice:app:0", "doc:readme:alice:lib:0"]
    assert 0 < fake_redis.ttl(keys[0]) <= DATA_TTL_SECONDS
    assert json.loads(fake_redis.get("cache:embed:alice:app"))["sha"] == "sha1"


def test_unchanged_readmes_skip_the_embedding_api(embedder):
    repos = [_repo("app", "sha1"), _repo("lib", "sha2")]
    svc.embed_and_store("alice", repos)
    calls_after_first_run = embedder.embedded

    stats = svc.embed_and_store("alice", repos)

    assert stats["repos_cached"] == 2
    assert embedder.embedded == calls_after_first_run


def test_changed_readme_is_re_embedded(embedder):
    svc.embed_and_store("alice", [_repo("app", "sha1"), _repo("lib", "sha2")])

    stats = svc.embed_and_store("alice", [_repo("app", "sha1"), _repo("lib", "sha2-new")])

    assert stats["repos_cached"] == 1
    assert stats["repos_embedded"] == 1


def test_cache_hit_with_missing_vectors_re_embeds(embedder, fake_redis):
    svc.embed_and_store("alice", [_repo("app", "sha1")])
    fake_redis.delete("doc:readme:alice:app:0")  # e.g. evicted by Redis

    stats = svc.embed_and_store("alice", [_repo("app", "sha1")])

    assert stats["repos_embedded"] == 1
    assert _doc_keys(fake_redis, "alice") == ["doc:readme:alice:app:0"]


def test_repos_that_drop_out_are_pruned(embedder, fake_redis):
    svc.embed_and_store("alice", [_repo("app", "sha1"), _repo("old", "sha2")])

    svc.embed_and_store("alice", [_repo("app", "sha1")])

    assert _doc_keys(fake_redis, "alice") == ["doc:readme:alice:app:0"]
    assert fake_redis.get("cache:embed:alice:old") is None


def test_other_users_are_left_alone(embedder, fake_redis):
    svc.embed_and_store("alice", [_repo("app", "sha1")])

    svc.embed_and_store("bob", [_repo("tool", "sha9")])

    assert _doc_keys(fake_redis, "alice") == ["doc:readme:alice:app:0"]


def test_rate_limit_pause_is_reported_as_progress(embedder):
    embedder.pause_seconds = 35.0
    updates = []

    svc.embed_and_store(
        "alice",
        [_repo("app", "sha1")],
        progress_callback=lambda phase, detail: updates.append(detail),
    )

    paused = [update for update in updates if "wait_seconds" in update]
    assert paused[0]["wait_seconds"] == 35
    assert paused[0]["current_repo"] == "app"


# ── Background job ───────────────────────────────────────────────────


def _fake_profile(repos):
    async def analyze_profile(username):
        return {
            "profile": {"username": username, "name": "Alice", "public_repos": len(repos)},
            "repositories": [
                {**r, "description": None, "language": "Python", "stars": 1, "forks": 0, "url": ""}
                for r in repos
            ],
        }
    return analyze_profile


def test_background_job_completes_and_releases_lock(embedder, fake_redis, monkeypatch):
    monkeypatch.setattr(github_api, "analyze_profile", _fake_profile([_repo("app", "sha1")]))
    fake_redis.set("lock:analyze:alice", "1")

    github_api.run_indexing_task("alice")

    status = json.loads(fake_redis.get("status:analyze:alice"))
    assert status["status"] == "completed"
    assert status["profile"]["repositories"][0]["name"] == "app"
    assert fake_redis.exists("lock:analyze:alice") == 0


def test_background_job_failure_shows_safe_message(fake_redis, monkeypatch):
    async def missing_user(username):
        raise GitHubError("GitHub user 'ghost' not found.")

    monkeypatch.setattr(github_api, "analyze_profile", missing_user)
    fake_redis.set("lock:analyze:ghost", "1")

    github_api.run_indexing_task("ghost")

    status = json.loads(fake_redis.get("status:analyze:ghost"))
    assert status == {"status": "failed", "phase": "failed", "error": "GitHub user 'ghost' not found."}
    assert fake_redis.exists("lock:analyze:ghost") == 0


def test_unexpected_error_details_stay_on_the_server(fake_redis, monkeypatch):
    async def boom(username):
        raise RuntimeError("https://internal.example/?key=SECRET")

    monkeypatch.setattr(github_api, "analyze_profile", boom)

    github_api.run_indexing_task("alice")

    status = json.loads(fake_redis.get("status:analyze:alice"))
    assert status["status"] == "failed"
    assert "SECRET" not in status["error"]
