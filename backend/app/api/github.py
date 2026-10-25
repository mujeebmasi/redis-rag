"""
GitHub API Routes
=================
Endpoints for analyzing GitHub profiles.

Endpoints:
    POST /github/analyze → Queue background indexing of a GitHub profile
    GET  /github/status/{username} → Poll indexing progress

This is the first step before chatting — you must analyze a profile
before you can ask questions about it.

Redis keys used here:
    status:analyze:{username} → JSON: status, phase, progress, profile
    lock:analyze:{username}   → exists while an indexing job is running
"""

import asyncio
import json
import logging
import time

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from redis.exceptions import RedisError

from app.core.errors import UserFacingError
from app.core.indexing_config import (
    DATA_TTL_SECONDS,
    LOCK_TTL_SECONDS,
    STATUS_TTL_SECONDS,
)
from app.core.redis_client import redis_client
from app.schemas.github import (
    GitHubAnalyzeRequest,
    GitHubAnalyzeResponse,
    GitHubProfileResponse,
    GitHubStatusResponse,
    RepositoryInfo,
)
from app.services.embedding_service import embed_and_store, log_to_redis
from app.services.github_service import analyze_profile, is_valid_username

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/github",
    tags=["GitHub"],
)

REDIS_DOWN_MESSAGE = (
    "The Redis database is unreachable right now. "
    "Check the REDIS_HOST / REDIS_PORT / REDIS_PASSWORD settings on the server."
)


def normalize_username(username: str) -> str:
    """Lowercase + trim a username, and reject anything that isn't a GitHub username."""
    username = username.strip().lower()
    if not is_valid_username(username):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="That doesn't look like a GitHub username (letters, numbers and hyphens only).",
        )
    return username


def _status_key(username: str) -> str:
    return f"status:analyze:{username}"


def _lock_key(username: str) -> str:
    return f"lock:analyze:{username}"


# ── Background Task ─────────────────────────────────────────────────


def _update_status(status_key: str, data: dict, ttl: int = STATUS_TTL_SECONDS) -> None:
    """Safely write status JSON to Redis, swallowing errors."""
    try:
        redis_client.set(status_key, json.dumps(data), ex=ttl)
    except RedisError as e:
        logger.error(f"Failed to write status to Redis: {e}")


def run_indexing_task(username: str) -> None:
    """
    Background task to fetch details from GitHub and store embeddings in Redis.

    Updates granular progress at each phase:
    - fetching: downloading repos from GitHub
    - embedding: per-repo chunking and vector generation
    - saving: finalizing results
    - completed / failed: terminal states

    The job owns lock:analyze:{username} until it ends (see analyze_github_profile).
    """
    status_key = _status_key(username)
    lock_key = _lock_key(username)
    log_to_redis(username, f"Background task started for {username}.")

    try:
        # ── Phase 1: Fetch from GitHub ───────────────────────────
        _update_status(
            status_key,
            {
                "status": "processing",
                "phase": "fetching",
                "progress": {"detail": "Fetching repositories from GitHub..."},
                "timestamp": time.time(),
            },
        )

        logger.info(f"Background indexing started for '{username}'")
        result = asyncio.run(analyze_profile(username))

        repos = result["repositories"]
        indexable = [r for r in repos if r.get("readme") and r["readme"].strip()]
        log_to_redis(username, f"GitHub fetch complete. Found {len(repos)} repos, {len(indexable)} have READMEs.")

        _update_status(
            status_key,
            {
                "status": "processing",
                "phase": "embedding",
                "progress": {
                    "repos_total": len(indexable),
                    "repos_done": 0,
                    "chunks_done": 0,
                    "detail": f"Fetched {len(repos)} repos, {len(indexable)} have READMEs",
                },
                "timestamp": time.time(),
            },
        )

        # ── Phase 2: Embed and store ─────────────────────────────
        def progress_callback(phase: str, detail: dict) -> None:
            """Called by embed_and_store to report per-repo progress."""
            _update_status(
                status_key,
                {
                    "status": "processing",
                    "phase": phase,
                    "progress": detail,
                    "timestamp": time.time(),
                },
            )
            # Still working → keep holding the lock
            redis_client.expire(lock_key, LOCK_TTL_SECONDS)

        stats = embed_and_store(
            username=username,
            repositories=repos,
            progress_callback=progress_callback,
        )

        # ── Phase 3: Build response metadata ─────────────────────
        profile = result["profile"]
        readmes_count = len(indexable)

        repositories = [
            RepositoryInfo(
                name=repo["name"],
                description=repo.get("description"),
                language=repo.get("language"),
                stars=repo.get("stars", 0),
                forks=repo.get("forks", 0),
                url=repo.get("url", ""),
                has_readme=repo.get("readme") is not None,
            )
            for repo in repos
        ]

        cache_detail = ""
        if stats["repos_cached"] > 0:
            cache_detail = (
                f" ({stats['repos_cached']} unchanged, "
                f"{stats['repos_embedded']} newly embedded)"
            )

        profile_data = GitHubProfileResponse(
            username=profile["username"],
            name=profile.get("name"),
            bio=profile.get("bio"),
            avatar_url=profile.get("avatar_url"),
            public_repos=profile.get("public_repos", 0),
            followers=profile.get("followers", 0),
            following=profile.get("following", 0),
            repositories=repositories,
            total_readmes_indexed=readmes_count,
            message=f"Profile analyzed! {readmes_count} READMEs indexed{cache_detail}.",
        )

        _update_status(
            status_key,
            {
                "status": "completed",
                "phase": "completed",
                "progress": stats,
                "profile": profile_data.model_dump(),
                "timestamp": time.time(),
            },
            ttl=DATA_TTL_SECONDS,
        )
        log_to_redis(username, "Task completed.")

    except UserFacingError as e:
        # GitHub / Gemini problems with a message written for the user
        log_to_redis(username, f"Task FAILED: {e}")
        _update_status(status_key, {"status": "failed", "phase": "failed", "error": str(e)})

    except RedisError as e:
        logger.error(f"Redis error while indexing {username}: {e}")
        _update_status(
            status_key,
            {"status": "failed", "phase": "failed", "error": "Lost the connection to Redis while indexing. Please try again."},
        )

    except Exception as e:
        # Unknown problem: full details go to the server log only
        log_to_redis(username, f"Task FAILED: {type(e).__name__}: {e}")
        logger.exception(f"Unexpected error in background indexing for {username}: {e}")
        _update_status(
            status_key,
            {"status": "failed", "phase": "failed", "error": "Something went wrong while indexing. Please try again."},
        )

    finally:
        try:
            redis_client.delete(lock_key)
        except RedisError:
            pass  # The lock expires on its own after LOCK_TTL_SECONDS


# ── Endpoints ────────────────────────────────────────────────────────


@router.post(
    "/analyze",
    response_model=GitHubAnalyzeResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def analyze_github_profile(
    data: GitHubAnalyzeRequest,
    background_tasks: BackgroundTasks,
):
    """
    Queue background task to analyze a GitHub profile and index its README files.

    - Already analyzed in the last 24h (and refresh=false) → returns "completed"
      right away; the result is served from Redis.
    - A job is already running for this user → returns "processing".
    - Otherwise → starts a background job and returns "processing".

    The client should poll GET /github/status/{username} to see the status.
    """
    username = normalize_username(data.username)
    status_key = _status_key(username)

    try:
        if not data.refresh:
            raw_status = redis_client.get(status_key)
            if raw_status and json.loads(raw_status).get("status") == "completed":
                return GitHubAnalyzeResponse(
                    username=username,
                    status="completed",
                    message="Profile was analyzed in the last 24 hours. Loaded from cache.",
                )

        # One job per user at a time. SET with NX ("only if it doesn't exist")
        # is atomic: if two requests arrive together, only one gets the lock.
        # EX makes the lock expire by itself if the server dies mid-job.
        got_lock = redis_client.set(
            _lock_key(username), str(time.time()), nx=True, ex=LOCK_TTL_SECONDS
        )
        if not got_lock:
            return GitHubAnalyzeResponse(
                username=username,
                status="processing",
                message="Profile analysis is already in progress.",
            )

        redis_client.set(
            status_key,
            json.dumps(
                {
                    "status": "processing",
                    "phase": "queued",
                    "progress": {"detail": "Task queued..."},
                    "timestamp": time.time(),
                }
            ),
            ex=STATUS_TTL_SECONDS,
        )
    except RedisError as e:
        logger.error(f"Redis unavailable in /github/analyze: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=REDIS_DOWN_MESSAGE,
        )

    background_tasks.add_task(run_indexing_task, username)

    return GitHubAnalyzeResponse(
        username=username,
        status="processing",
        message="Profile analysis task queued in background.",
    )


@router.get("/status/{username}", response_model=GitHubStatusResponse)
def get_analysis_status(username: str):
    """
    Get the status of the GitHub profile indexing task.

    Status can be:
    - 'not_started': No task has been initiated for this username.
    - 'processing': Ingestion task is currently running (check phase & progress).
    - 'completed': Vector DB is indexed and ready (returns profile metadata).
    - 'failed': Error occurred during fetching/embedding.
    """
    username = normalize_username(username)

    try:
        raw_status = redis_client.get(_status_key(username))
        job_running = bool(redis_client.exists(_lock_key(username)))
    except RedisError as e:
        logger.error(f"Redis unavailable in /github/status: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=REDIS_DOWN_MESSAGE,
        )

    if not raw_status:
        return GitHubStatusResponse(username=username, status="not_started")

    try:
        status_data = json.loads(raw_status)
    except ValueError:
        return GitHubStatusResponse(username=username, status="not_started")

    # The job holds the lock until it finishes. "processing" without a lock
    # means the job died (e.g. the server restarted during a deploy).
    if status_data.get("status") == "processing" and not job_running:
        return GitHubStatusResponse(
            username=username,
            status="failed",
            phase="failed",
            error="Indexing was interrupted (the server restarted). Click Analyze to try again.",
        )

    return GitHubStatusResponse(
        username=username,
        status=status_data.get("status", "unknown"),
        phase=status_data.get("phase"),
        progress=status_data.get("progress"),
        error=status_data.get("error"),
        profile=status_data.get("profile"),
    )
