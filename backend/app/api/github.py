"""
GitHub API Routes
=================
Endpoints for analyzing GitHub profiles.

Endpoints:
    POST /github/analyze → Fetch a GitHub profile, extract READMEs,
                           and store embeddings in Redis Vector DB

This is the first step before chatting — you must analyze a profile
before you can ask questions about it.
"""

import asyncio
import json
import logging
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
import httpx

from app.core.auth import get_current_user
from app.core.redis_client import redis_client
from app.schemas.github import (
    GitHubAnalyzeRequest,
    GitHubProfileResponse,
    GitHubAnalyzeResponse,
    GitHubStatusResponse,
    RepositoryInfo,
)
from app.services.github_service import analyze_profile
from app.services.embedding_service import embed_and_store

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/github",
    tags=["GitHub"],
)


def run_indexing_task(username: str):
    """
    Background task to fetch details from GitHub and store embeddings in Redis.
    Updates progress state under status:analyze:{username} in Redis.
    """
    status_key = f"status:analyze:{username}"
    try:
        print(f"DEBUG: Background task started for user '{username}'", flush=True)
        # Step 1-3: Fetch profile and repositories concurrently
        result = asyncio.run(analyze_profile(username))
        
        repos = result["repositories"]
        print(f"DEBUG: GitHub fetch complete. Found {len(repos)} public repositories.", flush=True)
        
        # Step 4: Generate embeddings and store in Redis Vector DB
        print(f"DEBUG: Starting chunking and embedding generation...", flush=True)
        total_chunks = embed_and_store(
            username=username,
            repositories=repos,
        )
        print(f"DEBUG: Ingestion complete. Stored {total_chunks} chunks in Redis.", flush=True)
        
        # Calculate how many readmes were indexed
        readmes_count = sum(1 for r in repos if r["readme"])
        
        # Step 5: Construct complete response metadata and cache it
        profile = result["profile"]
        repositories = [
            RepositoryInfo(
                name=repo["name"],
                description=repo["description"],
                language=repo["language"],
                stars=repo["stars"],
                forks=repo["forks"],
                url=repo["url"],
                has_readme=repo["readme"] is not None,
            )
            for repo in result["repositories"]
        ]
        
        profile_data = GitHubProfileResponse(
            username=profile["username"],
            name=profile["name"],
            bio=profile["bio"],
            avatar_url=profile["avatar_url"],
            public_repos=profile["public_repos"],
            followers=profile["followers"],
            following=profile["following"],
            repositories=repositories,
            total_readmes_indexed=readmes_count,
            message=f"Profile analyzed! {readmes_count} READMEs indexed ({total_chunks} chunks stored in vector DB).",
        )
        
        status_data = {
            "status": "completed",
            "profile": profile_data.model_dump(),
        }
        redis_client.set(status_key, json.dumps(status_data), ex=86400)  # Cache completed task for 24h
        
    except httpx.HTTPStatusError as e:
        error_msg = f"GitHub API error: {e.response.status_code}"
        if e.response.status_code == 404:
            error_msg = f"GitHub user '{username}' not found."
        redis_client.set(status_key, json.dumps({"status": "failed", "error": error_msg}), ex=3600)
    except httpx.RequestError:
        error_msg = "Could not connect to GitHub API. Check connection."
        redis_client.set(status_key, json.dumps({"status": "failed", "error": error_msg}), ex=3600)
    except Exception as e:
        logger.exception(f"Unexpected error in background indexing for {username}: {e}")
        redis_client.set(status_key, json.dumps({"status": "failed", "error": str(e)}), ex=3600)


@router.post("/analyze", response_model=GitHubAnalyzeResponse, status_code=status.HTTP_202_ACCEPTED)
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
    
    # Check if a task is already processing
    raw_status = redis_client.get(status_key)
    if raw_status:
        try:
            status_data = json.loads(raw_status)
            if status_data.get("status") == "processing":
                return GitHubAnalyzeResponse(
                    username=username,
                    status="processing",
                    message="Profile analysis is already in progress.",
                )
        except Exception:
            pass
            
    # Set status to processing and dispatch background task
    redis_client.set(status_key, json.dumps({"status": "processing"}), ex=3600)
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
    - 'processing': Ingestion task is currently running.
    - 'completed': Vector DB is indexed and ready (returns profile metadata).
    - 'failed': Error occurred during fetching/embedding.
    
    Requires: JWT Authentication (Bearer token)
    """
    username = username.lower().strip()
    status_key = f"status:analyze:{username}"
    
    raw_status = redis_client.get(status_key)
    if not raw_status:
        return GitHubStatusResponse(
            username=username,
            status="not_started",
            error=None,
            profile=None,
        )
        
    try:
        status_data = json.loads(raw_status)
        return GitHubStatusResponse(
            username=username,
            status=status_data.get("status"),
            error=status_data.get("error"),
            profile=status_data.get("profile"),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to parse status data: {str(e)}",
        )
