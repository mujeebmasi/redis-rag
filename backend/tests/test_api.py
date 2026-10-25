"""
HTTP endpoint tests (FastAPI TestClient + fakeredis).
"""

import json

import pytest
import redis
from fastapi.testclient import TestClient

import app.api.chat as chat_api
import app.api.github as github_api
from app.main import app
from app.services.embedding_service import EmbeddingError

client = TestClient(app)


@pytest.fixture
def started_jobs(fake_redis, monkeypatch):
    """Record background jobs instead of running them."""
    started = []
    monkeypatch.setattr(github_api, "run_indexing_task", started.append)
    return started


def test_invalid_username_is_rejected(started_jobs):
    response = client.post("/github/analyze", json={"username": "not a user!"})

    assert response.status_code == 400
    assert started_jobs == []


def test_analyze_starts_one_job_and_takes_the_lock(fake_redis, started_jobs):
    response = client.post("/github/analyze", json={"username": "  Alice "})

    assert response.status_code == 202
    assert response.json()["status"] == "processing"
    assert started_jobs == ["alice"]
    assert fake_redis.exists("lock:analyze:alice")


def test_second_click_while_running_does_not_start_another_job(started_jobs):
    client.post("/github/analyze", json={"username": "alice"})

    response = client.post("/github/analyze", json={"username": "alice"})

    assert response.json()["message"] == "Profile analysis is already in progress."
    assert started_jobs == ["alice"]


def test_recent_result_is_served_from_cache(fake_redis, started_jobs):
    fake_redis.set("status:analyze:alice", json.dumps({"status": "completed"}))

    response = client.post("/github/analyze", json={"username": "alice"})

    assert response.json()["status"] == "completed"
    assert started_jobs == []


def test_refresh_re_indexes_even_when_cached(fake_redis, started_jobs):
    fake_redis.set("status:analyze:alice", json.dumps({"status": "completed"}))

    response = client.post("/github/analyze", json={"username": "alice", "refresh": True})

    assert response.json()["status"] == "processing"
    assert started_jobs == ["alice"]


def test_status_of_a_job_that_died_is_reported_as_failed(fake_redis):
    # "processing" but no lock → the server restarted mid-job
    fake_redis.set("status:analyze:alice", json.dumps({"status": "processing"}))

    response = client.get("/github/status/alice")

    assert response.json()["status"] == "failed"
    assert "interrupted" in response.json()["error"]


def test_status_of_a_running_job(fake_redis):
    fake_redis.set("status:analyze:alice", json.dumps({"status": "processing", "phase": "embedding"}))
    fake_redis.set("lock:analyze:alice", "1")

    response = client.get("/github/status/alice")

    assert response.json()["status"] == "processing"
    assert response.json()["phase"] == "embedding"


class DeadRedis:
    """Every command fails like an unreachable Redis does."""

    def __getattr__(self, name):
        def fail(*args, **kwargs):
            raise redis.ConnectionError("Error -2 connecting to secret-host.redis.io:10037")
        return fail


def test_unreachable_redis_gives_503_without_hostname(monkeypatch):
    monkeypatch.setattr(github_api, "redis_client", DeadRedis())

    response = client.post("/github/analyze", json={"username": "alice"})

    assert response.status_code == 503
    assert "secret-host" not in response.text


def test_chat_shows_user_facing_errors(monkeypatch):
    def ask(username, question):
        raise EmbeddingError("Gemini embedding API rate limit reached. Please wait a minute and try again.")

    monkeypatch.setattr(chat_api, "ask", ask)

    response = client.post("/chat", json={"username": "alice", "question": "hi"})

    assert response.status_code == 502
    assert "rate limit" in response.json()["detail"]


def test_chat_hides_unexpected_error_details(monkeypatch):
    def ask(username, question):
        raise RuntimeError("https://api.example/?key=SECRET")

    monkeypatch.setattr(chat_api, "ask", ask)

    response = client.post("/chat", json={"username": "alice", "question": "hi"})

    assert response.status_code == 500
    assert "SECRET" not in response.text


def test_empty_question_is_rejected():
    response = client.post("/chat", json={"username": "alice", "question": "   "})

    assert response.status_code == 400


def test_health_reports_keys_without_values(fake_redis):
    response = client.get("/health")

    body = response.json()
    assert body["redis"] != "unreachable"
    assert set(body) == {"status", "redis", "gemini_key_set", "groq_key_set", "github_token_set"}
