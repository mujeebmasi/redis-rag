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

from fastapi import APIRouter, Depends, HTTPException, status
import httpx

from app.core.auth import get_current_user
from app.schemas.github import GitHubAnalyzeRequest, GitHubProfileResponse, RepositoryInfo
from app.services.github_service import analyze_profile
from app.services.embedding_service import embed_and_store

router = APIRouter(
    prefix="/github",
    tags=["GitHub"],
)


@router.post("/analyze", response_model=GitHubProfileResponse)
def analyze_github_profile(
    data: GitHubAnalyzeRequest,
    user: dict = Depends(get_current_user),
):
    """
    Analyze a GitHub profile and index its README files.
    
    Steps:
    1. Fetch user profile from GitHub API
    2. Fetch all public repositories
    3. Download README files
    4. Generate embeddings and store in Redis Vector DB
    5. Return profile summary
    
    Requires: JWT Authentication (Bearer token)
    """

    try:
        # Step 1-3: Fetch everything from GitHub
        result = analyze_profile(data.username)

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"GitHub user '{data.username}' not found.",
            )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"GitHub API error: {e.response.status_code}",
        )

    except httpx.RequestError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not connect to GitHub API. Check your internet connection.",
        )

    # Step 4: Embed and store READMEs in Redis
    try:
        total_chunks = embed_and_store(
            username=data.username,
            repositories=result["repositories"],
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Embedding/Redis error: {str(e)}",
        )

    # Step 5: Build response
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

    readmes_count = sum(1 for r in result["repositories"] if r["readme"])

    return GitHubProfileResponse(
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
