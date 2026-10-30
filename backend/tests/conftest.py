"""
Shared test setup.

Tests never touch a real Redis, GitHub, Gemini or Groq:
- Redis   → fakeredis (an in-memory Redis written in Python)
- HTTP    → httpx.MockTransport or monkeypatched functions

fakeredis has no RediSearch (FT.*) commands, so tests that store
vectors switch off index creation and test everything around it.
"""

import fakeredis
import pytest

import app.api.github as github_api
import app.main as main
import app.services.embedding_service as embedding_service
import app.services.rag_service as rag_service


@pytest.fixture
def fake_redis(monkeypatch):
    """Replace both Redis clients everywhere with one shared fake server."""
    server = fakeredis.FakeServer()
    text_client = fakeredis.FakeRedis(server=server, decode_responses=True)
    raw_client = fakeredis.FakeRedis(server=server)

    monkeypatch.setattr(github_api, "redis_client", text_client)
    monkeypatch.setattr(main, "redis_client", text_client)
    monkeypatch.setattr(rag_service, "redis_client", text_client)
    monkeypatch.setattr(embedding_service, "redis_client", text_client)
    monkeypatch.setattr(embedding_service, "redis_client_raw", raw_client)
    return text_client


@pytest.fixture
def no_sleep(monkeypatch):
    """Make retry backoff instant. Returns the pauses that would have happened."""
    pauses = []
    monkeypatch.setattr(embedding_service.time, "sleep", pauses.append)
    return pauses
