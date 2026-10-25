"""
GitHub Service
==============
Fetches data from the GitHub API.

This service handles all communication with GitHub:
1. Fetch user profile (bio, avatar, repo count)
2. Fetch public repositories (name, language, stars, forks)
3. Fetch README files (decoded from base64)
4. Filter & rank repositories by quality signals

GitHub API Docs: https://docs.github.com/en/rest

Rate Limits:
- Without token: 60 requests/hour
- With token: 5,000 requests/hour
- Set GITHUB_TOKEN in .env for higher limits
"""

import asyncio
import base64
import logging
import re
import time

import httpx

from app.core.config import settings
from app.core.errors import UserFacingError
from app.core.indexing_config import (
    MAX_REPOS_TO_INDEX,
    MIN_README_LENGTH,
    SKIP_ARCHIVED,
    SKIP_FORKS,
)

logger = logging.getLogger(__name__)

# GitHub API base URL
GITHUB_API = "https://api.github.com"

# GitHub usernames: letters, digits and hyphens, at most 39 characters.
# Checking this up front also keeps usernames safe to use inside Redis keys.
_USERNAME_RE = re.compile(r"^[A-Za-z0-9-]{1,39}$")


class GitHubError(UserFacingError):
    """A GitHub problem whose message is safe to show to the user."""


def is_valid_username(username: str) -> bool:
    """Return True if the string looks like a GitHub username."""
    return bool(_USERNAME_RE.match(username))


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


def _check_rate_limit(response: httpx.Response) -> None:
    """
    Turn GitHub's rate-limit response into a clear message.

    GitHub answers 403 (with x-ratelimit-remaining: 0) or 429 when
    the hourly request budget is used up.
    """
    remaining = response.headers.get("x-ratelimit-remaining")
    if response.status_code == 429 or (
        response.status_code == 403 and remaining == "0"
    ):
        reset_at = int(response.headers.get("x-ratelimit-reset", "0") or 0)
        minutes = max(1, round((reset_at - time.time()) / 60)) if reset_at else 60
        raise GitHubError(
            f"GitHub API rate limit reached. Try again in about {minutes} min "
            "(setting GITHUB_TOKEN on the server raises the limit)."
        )


# ── Individual API Calls ─────────────────────────────────────────────


async def fetch_user_profile(client: httpx.AsyncClient, username: str) -> dict:
    """
    Fetch a GitHub user's profile information.

    API: GET /users/{username}

    Raises:
        GitHubError: If the user doesn't exist or the rate limit is hit
    """
    response = await client.get(f"{GITHUB_API}/users/{username}")
    _check_rate_limit(response)
    if response.status_code == 404:
        raise GitHubError(f"GitHub user '{username}' not found.")
    response.raise_for_status()
    return response.json()


async def fetch_repositories(
    client: httpx.AsyncClient, username: str, max_repos: int = 100
) -> list[dict]:
    """
    Fetch a user's public repositories, sorted by most recently updated.

    API: GET /users/{username}/repos

    Args:
        username: GitHub username
        max_repos: Maximum number of repos to fetch (default 100 — we
                   filter down to MAX_REPOS_TO_INDEX after scoring)
    """
    response = await client.get(
        f"{GITHUB_API}/users/{username}/repos",
        params={
            "sort": "updated",
            "direction": "desc",
            "per_page": min(max_repos, 100),
        },
    )
    _check_rate_limit(response)
    response.raise_for_status()
    return response.json()


async def fetch_readme(
    client: httpx.AsyncClient, owner: str, repo: str
) -> tuple[str | None, str | None]:
    """
    Fetch and decode the README file for a repository.

    API: GET /repos/{owner}/{repo}/readme

    GitHub returns README content as base64-encoded string.
    We decode it to plain text.

    Returns:
        (readme_text, readme_sha), or (None, None) if there is no README
        or it couldn't be fetched. One broken repo shouldn't fail the
        whole profile, so only the rate limit is raised.
    """
    try:
        response = await client.get(
            f"{GITHUB_API}/repos/{owner}/{repo}/readme"
        )
        _check_rate_limit(response)
        if response.status_code == 404:
            return None, None
        response.raise_for_status()

        data = response.json()
        content_b64 = data.get("content", "")
        readme_text = base64.b64decode(content_b64).decode(
            "utf-8", errors="replace"
        )

        # The README file's SHA changes only when the README changes,
        # so it works as a cache key for the embeddings.
        return readme_text, data.get("sha")

    except GitHubError:
        raise
    except (httpx.HTTPError, ValueError) as e:
        logger.warning(f"Could not fetch README for {owner}/{repo}: {e}")
        return None, None


# ── Filtering & Ranking ─────────────────────────────────────────────


def filter_and_rank_repos(
    raw_repos: list[dict],
    max_repos: int = MAX_REPOS_TO_INDEX,
    skip_forks: bool = SKIP_FORKS,
    skip_archived: bool = SKIP_ARCHIVED,
) -> list[dict]:
    """
    Filter out low-quality repos and rank by popularity.

    Steps:
    1. Remove forks (if configured)
    2. Remove archived repos (if configured)
    3. Sort by popularity score (stars + forks)
    4. Take top N repos
    """
    filtered = []
    for repo in raw_repos:
        if skip_forks and repo.get("fork", False):
            logger.debug(f"Skipping fork: {repo['name']}")
            continue
        if skip_archived and repo.get("archived", False):
            logger.debug(f"Skipping archived: {repo['name']}")
            continue
        filtered.append(repo)

    # Sort by popularity: stars + forks (descending)
    filtered.sort(
        key=lambda r: r.get("stargazers_count", 0) + r.get("forks_count", 0),
        reverse=True,
    )

    selected = filtered[:max_repos]
    logger.info(
        f"Filtered {len(raw_repos)} repos → {len(filtered)} eligible "
        f"→ {len(selected)} selected for indexing"
    )
    return selected


# ── Main Orchestrator ────────────────────────────────────────────────


async def analyze_profile(username: str) -> dict:
    """
    Full profile analysis — orchestrates all the above functions.

    Steps:
    1. Fetch user profile
    2. Fetch all public repositories
    3. Filter & rank repos by quality
    4. Fetch README for each selected repo concurrently
    5. Drop READMEs that are too short to be useful
    6. Package everything into a structured result

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
                    "readme": "# README content..." or None,
                    "readme_sha": "abc123..." or None,
                },
                ...
            ]
        }
    """

    async with httpx.AsyncClient(
        headers=_get_headers(), timeout=30.0
    ) as client:
        # Step 1: Get user profile
        profile = await fetch_user_profile(client, username)

        # Step 2: Get all repositories
        raw_repos = await fetch_repositories(client, username)

        # Step 3: Filter & rank
        selected_repos = filter_and_rank_repos(raw_repos)

        # Step 4: Fetch README for each selected repo concurrently
        tasks = [
            fetch_readme(client, username, repo["name"])
            for repo in selected_repos
        ]
        readme_results = await asyncio.gather(*tasks)

        # Step 5: Build structured data with quality filtering
        repositories = []
        for repo, (readme_content, readme_sha) in zip(
            selected_repos, readme_results
        ):
            # Skip repos with empty or too-short READMEs
            if readme_content and len(readme_content.strip()) < MIN_README_LENGTH:
                logger.debug(
                    f"Skipping {repo['name']}: README too short "
                    f"({len(readme_content.strip())} < {MIN_README_LENGTH} chars)"
                )
                readme_content = None
                readme_sha = None

            repositories.append(
                {
                    "name": repo["name"],
                    "description": repo.get("description"),
                    "language": repo.get("language"),
                    "stars": repo.get("stargazers_count", 0),
                    "forks": repo.get("forks_count", 0),
                    "url": repo.get("html_url", ""),
                    "readme": readme_content,
                    "readme_sha": readme_sha,
                }
            )

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
