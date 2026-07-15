"""
GitHub Service
==============
Fetches data from the GitHub API.

This service handles all communication with GitHub:
1. Fetch user profile (bio, avatar, repo count)
2. Fetch public repositories (name, language, stars, forks)
3. Fetch README files (decoded from base64)

GitHub API Docs: https://docs.github.com/en/rest

Rate Limits:
- Without token: 60 requests/hour
- With token: 5,000 requests/hour
- Set GITHUB_TOKEN in .env for higher limits
"""

import asyncio
import base64
import httpx
from app.core.config import settings

# GitHub API base URL
GITHUB_API = "https://api.github.com"


def _get_headers() -> dict:
    """
    Build request headers for GitHub API.
    
    Includes authentication token if GITHUB_TOKEN is set in .env.
    The token increases rate limits from 60 → 5,000 requests/hour.
    """
    headers = {
        "Accept": "application/vnd.github.v3+json",
    }

    if settings.GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {settings.GITHUB_TOKEN}"

    return headers


async def fetch_user_profile(client: httpx.AsyncClient, username: str) -> dict:
    """
    Fetch a GitHub user's profile information.
    
    API: GET /users/{username}
    
    Returns dict with: login, name, bio, avatar_url, public_repos,
    followers, following, etc.
    
    Raises:
        httpx.HTTPStatusError: If user not found (404) or API error
    """
    response = await client.get(f"{GITHUB_API}/users/{username}")
    response.raise_for_status()
    return response.json()


async def fetch_repositories(client: httpx.AsyncClient, username: str, max_repos: int = 30) -> list[dict]:
    """
    Fetch a user's public repositories, sorted by most recently updated.
    
    API: GET /users/{username}/repos
    
    Args:
        username: GitHub username
        max_repos: Maximum number of repos to fetch (default 30)
    
    Returns:
        List of repository dicts with: name, description, language,
        stargazers_count, forks_count, html_url, etc.
    """
    response = await client.get(
        f"{GITHUB_API}/users/{username}/repos",
        params={
            "sort": "updated",
            "direction": "desc",
            "per_page": max_repos,
        },
    )
    response.raise_for_status()
    return response.json()


async def fetch_readme(client: httpx.AsyncClient, owner: str, repo: str) -> str | None:
    """
    Fetch and decode the README file for a repository.
    
    API: GET /repos/{owner}/{repo}/readme
    
    GitHub returns README content as base64-encoded string.
    We decode it to plain text.
    
    Returns:
        str: The README content as plain text
        None: If no README exists (404)
    """
    try:
        response = await client.get(f"{GITHUB_API}/repos/{owner}/{repo}/readme")
        response.raise_for_status()

        data = response.json()
        # GitHub returns content as base64
        content_b64 = data.get("content", "")
        return base64.b64decode(content_b64).decode("utf-8")

    except httpx.HTTPStatusError as e:
        # Only swallow 404 Not Found since it means the repo has no README
        if e.response.status_code == 404:
            return None
        # Propagate other errors (like 403 Rate Limit or 401 Unauthorized)
        raise e


async def analyze_profile(username: str) -> dict:
    """
    Full profile analysis — orchestrates all the above functions.
    
    Steps:
    1. Fetch user profile
    2. Fetch all public repositories
    3. Fetch README for each repository concurrently
    4. Package everything into a structured result
    
    Returns:
        dict: {
            "profile": {...user info...},
            "repositories": [
                {
                    "name": "repo-name",
                    "description": "...",
                    "language": "Python",
                    "stars": 42,
                    "forks": 7,
                    "url": "https://github.com/...",
                    "readme": "# README content..." or None
                },
                ...
            ]
        }
    """

    async with httpx.AsyncClient(headers=_get_headers()) as client:
        # Step 1: Get user profile
        profile = await fetch_user_profile(client, username)

        # Step 2: Get repositories
        raw_repos = await fetch_repositories(client, username)

        # Step 3: Fetch README for each repo concurrently
        tasks = [fetch_readme(client, username, repo["name"]) for repo in raw_repos]
        readmes = await asyncio.gather(*tasks)

        # Step 4: Build structured data
        repositories = []
        for repo, readme_content in zip(raw_repos, readmes):
            repositories.append({
                "name": repo["name"],
                "description": repo.get("description"),
                "language": repo.get("language"),
                "stars": repo.get("stargazers_count", 0),
                "forks": repo.get("forks_count", 0),
                "url": repo.get("html_url", ""),
                "readme": readme_content,
            })

        return {
            "profile": {
                "username": profile.get("login"),
                "name": profile.get("name"),
                "bio": profile.get("bio"),
                "avatar_url": profile.get("avatar_url"),
                "public_repos": profile.get("public_repos", 0),
                "followers": profile.get("followers", 0),
                "following": profile.get("following", 0),
            },
            "repositories": repositories,
        }
