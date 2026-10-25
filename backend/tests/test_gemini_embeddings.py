import json

import httpx
import pytest

from app.services.embedding_service import EmbeddingError, GeminiEmbeddings

KEY = "test-key-123"
DIM = 8


def _gemini(handler):
    """A GeminiEmbeddings whose HTTP calls go to `handler` instead of Google."""
    return GeminiEmbeddings(
        api_key=KEY, dim=DIM, client=httpx.Client(transport=httpx.MockTransport(handler))
    )


def _batch_ok(request):
    count = len(json.loads(request.content)["requests"])
    return httpx.Response(200, json={"embeddings": [{"values": [0.1] * DIM}] * count})


def test_api_key_is_sent_in_header_not_url():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"embedding": {"values": [0.1] * DIM}})

    _gemini(handler).embed_query("hello")

    request = seen[0]
    assert request.headers["x-goog-api-key"] == KEY
    assert KEY not in str(request.url)
    body = json.loads(request.content)
    assert body["taskType"] == "RETRIEVAL_QUERY"
    assert body["outputDimensionality"] == DIM


def test_documents_are_embedded_in_batches(monkeypatch):
    import app.services.embedding_service as svc
    monkeypatch.setattr(svc, "EMBEDDING_BATCH_SIZE", 50)
    batch_sizes = []

    def handler(request):
        body = json.loads(request.content)
        batch_sizes.append(len(body["requests"]))
        assert body["requests"][0]["taskType"] == "RETRIEVAL_DOCUMENT"
        return _batch_ok(request)

    vectors = _gemini(handler).embed_documents([f"chunk {i}" for i in range(120)])

    assert batch_sizes == [50, 50, 20]
    assert len(vectors) == 120


def test_rate_limit_is_retried_then_succeeds(no_sleep):
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) < 3:
            return httpx.Response(429)
        return _batch_ok(request)

    assert len(_gemini(handler).embed_documents(["a"])) == 1
    assert len(calls) == 3


def test_bad_request_is_not_retried_and_hides_the_key(no_sleep):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(400, json={"error": {"message": "API key not valid"}})

    with pytest.raises(EmbeddingError) as error:
        _gemini(handler).embed_query("hello")

    assert len(calls) == 1
    assert KEY not in str(error.value)


def test_wrong_vector_size_is_rejected():
    def handler(request):
        return httpx.Response(200, json={"embedding": {"values": [0.1] * 3072}})

    with pytest.raises(EmbeddingError, match="3072"):
        _gemini(handler).embed_query("hello")


def test_missing_api_key_gives_clear_error():
    with pytest.raises(EmbeddingError, match="GOOGLE_API_KEY"):
        GeminiEmbeddings(api_key="").embed_query("hello")
