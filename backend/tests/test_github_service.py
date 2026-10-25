import asyncio
import base64
import time

import httpx
import pytest

from app.services.github_service import (
    GitHubError,
    _check_rate_limit,
    fetch_readme,
    fetch_user_profile,
    filter_and_rank_repos,
    is_valid_username,
)


def _repo(name, stars=0, forks=0, fork=False, archived=False):
    return {
        "name": name,
        "stargazers_count": stars,
        "forks_count": forks,
        "fork": fork,
        "archived": archived,
    }


def test_filter_skips_forks_and_archived_and_ranks_by_popularity():
    repos = [
        _repo("small", stars=1),
        _repo("forked", stars=100, fork=True),
        _repo("old", stars=50, archived=True),
        _repo("popular", stars=10, forks=5),
        _repo("medium", stars=3),
    ]

    selected = filter_and_rank_repos(repos, max_repos=2)

    assert [r["name"] for r in selected] == ["popular", "medium"]


@pytest.mark.parametrize("name", ["torvalds", "mujeebmasi", "a-b-c", "A1"])
def test_valid_usernames(name):
    assert is_valid_username(name)


@pytest.mark.parametrize("name", ["", "has space", "a:b", "x" * 40, "../etc", "user*"])
def test_invalid_usernames(name):
    assert not is_valid_username(name)


def test_rate_limit_403_becomes_a_clear_error():
    response = httpx.Response(
        403,
        headers={
            "x-ratelimit-remaining": "0",
            "x-ratelimit-reset": str(int(time.time()) + 600),
        },
    )
    with pytest.raises(GitHubError, match="rate limit"):
        _check_rate_limit(response)


def test_other_403_is_not_a_rate_limit():
    _check_rate_limit(httpx.Response(403, headers={"x-ratelimit-remaining": "42"}))


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_unknown_user_gives_not_found_message():
    async def run():
        async with _client(lambda request: httpx.Response(404)) as client:
            await fetch_user_profile(client, "nobody")

    with pytest.raises(GitHubError, match="not found"):
        asyncio.run(run())


def test_readme_is_decoded_with_its_sha():
    body = {"content": base64.b64encode("# Hello\nworld".encode()).decode(), "sha": "abc123"}

    async def run():
        async with _client(lambda request: httpx.Response(200, json=body)) as client:
            return await fetch_readme(client, "me", "repo")

    assert asyncio.run(run()) == ("# Hello\nworld", "abc123")


@pytest.mark.parametrize("status_code", [404, 500])
def test_missing_or_broken_readme_does_not_fail_the_profile(status_code):
    async def run():
        async with _client(lambda request: httpx.Response(status_code)) as client:
            return await fetch_readme(client, "me", "repo")

    assert asyncio.run(run()) == (None, None)
