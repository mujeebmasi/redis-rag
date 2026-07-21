"""
GitHub Schemas
==============
Pydantic models for the GitHub analysis API.
"""

from pydantic import BaseModel


class GitHubAnalyzeRequest(BaseModel):
    """Request body for POST /github/analyze"""
    username: str


class RepositoryInfo(BaseModel):
    """Information about a single GitHub repository."""
    name: str
    description: str | None = None
    language: str | None = None
    stars: int = 0
    forks: int = 0
    url: str
    has_readme: bool = False


class GitHubProfileResponse(BaseModel):
    """Full response from the GitHub analysis endpoint."""
    username: str
    name: str | None = None
    bio: str | None = None
    avatar_url: str | None = None
    public_repos: int = 0
    followers: int = 0
    following: int = 0
    repositories: list[RepositoryInfo] = []
    total_readmes_indexed: int = 0
    message: str = "Profile analyzed successfully"


class GitHubAnalyzeResponse(BaseModel):
    """Response returned immediately when analysis is queued."""
    username: str
    status: str
    message: str


class GitHubStatusResponse(BaseModel):
    """
    Status of the GitHub profile indexing task.

    Fields:
    - status: "not_started" | "processing" | "completed" | "failed"
    - phase: Current processing phase (queued, fetching, embedding, saving, completed, failed)
    - progress: Granular progress info (repos_done, repos_total, chunks_done, current_repo, detail)
    - error: Error message if status is "failed"
    - profile: Full profile data if status is "completed"
    """
    username: str
    status: str
    phase: str | None = None
    progress: dict | None = None
    error: str | None = None
    profile: GitHubProfileResponse | None = None
