"""
GitHub API Routes
=================
Endpoints for analyzing GitHub profiles.

Endpoints:
    POST /github/analyze → Queue background indexing of a GitHub profile
    GET  /github/status/{username} → Poll indexing progress

This is the first step before chatting — you must analyze a profile
before you can ask questions about it.
"""

import asyncio
import json
import logging
import time

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from app.core.auth import get_current_user
from app.core.indexing_config import CACHE_TTL_SECONDS
from app.core.redis_client import redis_client
from app.schemas.github import (
    GitHubAnalyzeRequest,
    GitHubAnalyzeResponse,
    GitHubProfileResponse,
    GitHubStatusResponse,
    RepositoryInfo,
)
from app.services.embedding_service import embed_and_store
from app.services.github_service import analyze_profile

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/github",
    tags=["GitHub"],
)


# ── Background Task ─────────────────────────────────────────────────


def _update_status(status_key: str, data: dict, ttl: int = 3600) -> None:
    """Safely write status JSON to Redis, swallowing errors."""
    try:
        redis_client.set(status_key, json.dumps(data), ex=ttl)
    except Exception as e:
        logger.error(f"Failed to write status to Redis: {e}")


def run_indexing_task(username: str) -> None:
    """
    Background task to fetch details from GitHub and store embeddings in Redis.

    Updates granular progress at each phase:
    - fetching: downloading repos from GitHub
    - embedding: per-repo chunking and vector generation
    - saving: finalizing results
    - completed / failed: terminal states
    """
    status_key = f"status:analyze:{username}"

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
        logger.info(
            f"GitHub fetch complete: {len(repos)} repos fetched, "
            f"{len(indexable)} have indexable READMEs."
        )

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

        stats = embed_and_store(
            username=username,
            repositories=repos,
            progress_callback=progress_callback,
        )

        total_chunks = stats["total_chunks"]
        repos_embedded = stats["repos_embedded"]
        repos_cached = stats["repos_cached"]

        # ── Phase 3: Build response metadata ─────────────────────
        readmes_count = sum(1 for r in repos if r.get("readme"))
        profile = result["profile"]

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
        if repos_cached > 0:
            cache_detail = f" ({repos_cached} cached, {repos_embedded} newly embedded)"

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
            message=(
                f"Profile analyzed! {readmes_count} READMEs indexed "
                f"({total_chunks} chunks stored){cache_detail}."
            ),
        )

        _update_status(
            status_key,
            {
                "status": "completed",
                "phase": "completed",
                "progress": {
                    "repos_embedded": repos_embedded,
                    "repos_cached": repos_cached,
                    "total_chunks": total_chunks,
                },
                "profile": profile_data.model_dump(),
            },
            ttl=CACHE_TTL_SECONDS,
        )

        logger.info(
            f"Indexing complete for '{username}': "
            f"{total_chunks} chunks, {repos_embedded} embedded, "
            f"{repos_cached} cached."
        )

    except httpx.HTTPStatusError as e:
        error_msg = f"GitHub API error: {e.response.status_code}"
        if e.response.status_code == 404:
            error_msg = f"GitHub user '{username}' not found."
        _update_status(
            status_key,
            {"status": "failed", "phase": "failed", "error": error_msg},
        )

    except httpx.RequestError:
        _update_status(
            status_key,
            {
                "status": "failed",
                "phase": "failed",
                "error": "Could not connect to GitHub API. Check connection.",
            },
        )

    except Exception as e:
        logger.exception(
            f"Unexpected error in background indexing for {username}: {e}"
        )
        _update_status(
            status_key,
            {"status": "failed", "phase": "failed", "error": str(e)},
        )


# ── Endpoints ────────────────────────────────────────────────────────


@router.post(
    "/analyze",
    response_model=GitHubAnalyzeResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def analyze_github_profile(
    data: GitHubAnalyzeRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_user),
):
    """
    Queue background task to analyze a GitHub profile and index its README files.

    This is non-blocking and returns immediately with a status of 'processing'.
    The client should poll GET /github/status/{username} to see the status.

    Requires: JWT Authentication (Bearer token)
    """
    username = data.username.lower().strip()
    status_key = f"status:analyze:{username}"

    # Check if Redis is accessible
    try:
        raw_status = redis_client.get(status_key)
    except Exception as redis_err:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"Redis database is unreachable: {str(redis_err)}. "
                "Please ensure Redis container is running."
            ),
        )

    if raw_status:
        try:
            status_data = json.loads(raw_status)
            if status_data.get("status") == "processing":
                start_time = status_data.get("timestamp", 0)
                # If processing for < 30s, don't restart
                if time.time() - start_time < 30:
                    return GitHubAnalyzeResponse(
                        username=username,
                        status="processing",
                        message="Profile analysis is already in progress.",
                    )
                else:
                    logger.info(
                        f"Auto-resetting stuck task for {username} "
                        f"(active > 30s)."
                    )
        except Exception:
            pass

    # Set status to processing and dispatch background task
    try:
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
            ex=3600,
        )
    except Exception as redis_err:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"Redis database write error: {str(redis_err)}. "
                "Please ensure Redis container is running."
            ),
        )

    background_tasks.add_task(run_indexing_task, username)

    return GitHubAnalyzeResponse(
        username=username,
        status="processing",
        message="Profile analysis task queued in background.",
    )


@router.get("/status/{username}", response_model=GitHubStatusResponse)
def get_analysis_status(
    username: str,
    user: dict = Depends(get_current_user),
):
    """
    Get the status of the GitHub profile indexing task.

    Status can be:
    - 'not_started': No task has been initiated for this username.
    - 'processing': Ingestion task is currently running (check phase & progress).
    - 'completed': Vector DB is indexed and ready (returns profile metadata).
    - 'failed': Error occurred during fetching/embedding.

    Requires: JWT Authentication (Bearer token)
    """
    username = username.lower().strip()
    status_key = f"status:analyze:{username}"

    try:
        raw_status = redis_client.get(status_key)
    except Exception as redis_err:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Redis unreachable: {str(redis_err)}",
        )

    if not raw_status:
        return GitHubStatusResponse(
            username=username,
            status="not_started",
        )

    try:
        status_data = json.loads(raw_status)
        return GitHubStatusResponse(
            username=username,
            status=status_data.get("status", "unknown"),
            phase=status_data.get("phase"),
            progress=status_data.get("progress"),
            error=status_data.get("error"),
            profile=status_data.get("profile"),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to parse status data: {str(e)}",
        )
