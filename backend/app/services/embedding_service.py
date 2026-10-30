"""
Embedding Service
=================
The core of the RAG pipeline — converts text into vectors and stores them in Redis.

What is an Embedding?
- A list of numbers (e.g., [0.1, -0.3, 0.7, ...]) that represents the *meaning* of text
- Similar text → similar numbers → found by vector search
- This is how "semantic search" works (searching by meaning, not keywords)

Pipeline (per repository):
    a. Check SHA cache — skip if README hasn't changed (and its vectors still exist)
    b. Chunk the README text
    c. Generate embedding vectors (batched, with retry)
    d. Replace the repo's old vectors in Redis
    e. Update SHA cache
    f. Report progress
Then, once per profile:
    g. Delete vectors of repos that are no longer indexed
    h. Reset the 24h expiry on everything this profile still uses

Redis keys written here:
    doc:readme:{username}:{repo}:{i}  → hash: content, username, repo_name, embedding
    cache:embed:{username}:{repo}     → JSON: README sha, chunk count
    logs:analyze:{username}           → list of debug lines

Note: We use redis-py directly instead of langchain-redis to show
how vector search actually works at the Redis level.
"""

import json
import logging
import re
import time
from collections.abc import Callable

import httpx
import numpy as np
from redis.commands.search.field import TagField, TextField, VectorField
from redis.commands.search.index_definition import IndexDefinition, IndexType
from redis.commands.search.query import Query
from redis.exceptions import ResponseError

from app.core.config import settings
from app.core.errors import UserFacingError
from app.core.indexing_config import (
    CHAT_MAX_WAIT,
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    DATA_TTL_SECONDS,
    EMBEDDING_API_TIMEOUT,
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_DIM,
    EMBEDDING_MAX_RETRIES,
    EMBEDDING_MODEL,
    EMBEDDING_RATE_LIMIT_WAIT,
    INDEXING_MAX_WAIT,
    REDIS_PIPELINE_BATCH,
    STATUS_TTL_SECONDS,
    TOP_K,
)
from app.core.redis_client import redis_client, redis_client_raw

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────

INDEX_NAME = "idx:github_readmes"  # RediSearch index name
DOC_PREFIX = "doc:readme:"  # Key prefix for stored documents
CACHE_PREFIX = "cache:embed:"  # Key prefix for SHA cache


class EmbeddingError(UserFacingError):
    """The embedding API failed. The message never contains the API key."""


# Called with the number of seconds a request will pause for Gemini's rate limit.
RateLimitCallback = Callable[[float], None]


def log_to_redis(username: str, message: str) -> None:
    """Helper to write log messages to a Redis list for remote debugging."""
    try:
        key = f"logs:analyze:{username.lower().strip()}"
        redis_client.rpush(key, f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}")
        redis_client.expire(key, STATUS_TTL_SECONDS)
    except Exception:
        pass


# ── Text Splitter ────────────────────────────────────────────────────

def _split_text(text: str, chunk_size: int = None, chunk_overlap: int = None) -> list[str]:
    """
    Fast, zero-dependency recursive text splitter.

    Splits text by paragraphs first, then sentences, then words.
    No external imports — instant startup, no CPU cost.
    """
    if chunk_size is None:
        chunk_size = CHUNK_SIZE
    if chunk_overlap is None:
        chunk_overlap = CHUNK_OVERLAP

    if not text or not text.strip():
        return []

    separators = ["\n\n", "\n", ". ", "! ", "? ", "; ", ", ", " ", ""]

    def _split(text: str, seps: list[str]) -> list[str]:
        if not seps:
            # Split by character as last resort
            return [text[i:i+chunk_size] for i in range(0, len(text), chunk_size - chunk_overlap)]
        sep = seps[0]
        if sep == "":
            return [text[i:i+chunk_size] for i in range(0, len(text), chunk_size - chunk_overlap)]
        parts = text.split(sep)
        chunks = []
        current = ""
        for part in parts:
            candidate = current + (sep if current else "") + part
            if len(candidate) <= chunk_size:
                current = candidate
            else:
                if current:
                    chunks.append(current)
                if len(part) > chunk_size:
                    # Recursively split the oversized part
                    chunks.extend(_split(part, seps[1:]))
                    current = ""
                else:
                    current = part
        if current:
            chunks.append(current)
        return chunks

    raw_chunks = _split(text.strip(), separators)

    # Add overlap between consecutive chunks
    if chunk_overlap <= 0 or len(raw_chunks) <= 1:
        return [c for c in raw_chunks if c.strip()]

    overlapped = []
    for i, chunk in enumerate(raw_chunks):
        if i == 0:
            overlapped.append(chunk)
        else:
            # Prepend tail of previous chunk as context
            prev = raw_chunks[i - 1]
            tail = prev[-chunk_overlap:] if len(prev) > chunk_overlap else prev
            overlapped.append(tail + " " + chunk)
    return [c for c in overlapped if c.strip()]


# ── Embedding Model ─────────────────────────────────────────────────


def _rate_limit_wait(response: httpx.Response) -> float:
    """
    How long Gemini asks us to wait after a 429, in seconds.

    The free tier counts requests per minute, so a few seconds of backoff
    is not enough. The error body says how long to wait:
        {"error": {"details": [{"@type": "...RetryInfo", "retryDelay": "34s"}]}}
    If the body has no such hint, wait one full minute.
    """
    try:
        details = response.json()["error"]["details"]
        delays = [detail["retryDelay"] for detail in details if "retryDelay" in detail]
        return float(delays[0].removesuffix("s")) + 1  # +1s of margin
    except (ValueError, KeyError, TypeError, IndexError, AttributeError):
        return EMBEDDING_RATE_LIMIT_WAIT


class GeminiEmbeddings:
    """
    Small client for the Gemini embedding REST API.

    Why not the Google SDK?
    - The SDK looks up Google Cloud credentials at startup, which hangs
      on non-Google hosts like Render. Plain HTTP calls avoid that.

    Details that matter:
    - The API key goes in the `x-goog-api-key` header, never in the URL.
      URLs show up in logs and error messages; headers don't.
    - Documents and questions use different task types
      (RETRIEVAL_DOCUMENT / RETRIEVAL_QUERY), which Gemini tunes for search.
    - outputDimensionality=768 gives vectors 4x smaller than the default 3072,
      so far more profiles fit in a small Redis.
    - 5xx and network errors are retried with exponential backoff: 2s, 4s.
    - A 429 (rate limit) waits as long as Gemini asks. Indexing accepts
      waits up to INDEXING_MAX_WAIT; a chat question fails fast instead.
    """

    BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
    RETRY_STATUSES = {429, 500, 502, 503, 504}

    def __init__(
        self,
        api_key: str,
        model: str = EMBEDDING_MODEL,
        dim: int = EMBEDDING_DIM,
        client: httpx.Client | None = None,
    ):
        self.api_key = api_key
        self.model = model
        self.dim = dim
        self._client = client or httpx.Client(timeout=EMBEDDING_API_TIMEOUT)

    def _post(
        self,
        method: str,
        payload: dict,
        max_rate_limit_wait: float,
        on_rate_limit: RateLimitCallback | None = None,
    ) -> dict:
        """
        POST to the Gemini API, retrying transient failures.

        max_rate_limit_wait: the longest pause accepted after a 429.
        on_rate_limit: called before each rate-limit pause, so the caller can report it.
        """
        if not self.api_key:
            raise EmbeddingError("GOOGLE_API_KEY is not set on the server.")

        url = f"{self.BASE_URL}/{self.model}:{method}"
        headers = {"x-goog-api-key": self.api_key}
        problem = "unknown error"

        for attempt in range(1, EMBEDDING_MAX_RETRIES + 1):
            wait = 2**attempt  # 2s, 4s for network errors and 5xx
            try:
                response = self._client.post(url, json=payload, headers=headers)
            except httpx.TransportError as e:
                problem = f"network error ({type(e).__name__})"
            else:
                if response.status_code == 200:
                    return response.json()
                problem = f"HTTP {response.status_code}"
                # The body explains the error (bad key, quota...) and has no secrets.
                logger.warning(f"Gemini {method} returned {problem}: {response.text[:300]}")
                if response.status_code not in self.RETRY_STATUSES:
                    break  # Retrying won't fix a bad request or a bad key
                if response.status_code == 429:
                    wait = _rate_limit_wait(response)
                    if wait > max_rate_limit_wait:
                        break  # Too long to wait here (e.g. the daily quota is used up)

            if attempt < EMBEDDING_MAX_RETRIES:
                logger.warning(
                    f"Gemini {method} attempt {attempt}/{EMBEDDING_MAX_RETRIES} "
                    f"failed ({problem}). Retrying in {wait:.0f}s..."
                )
                if on_rate_limit and problem == "HTTP 429":
                    on_rate_limit(wait)
                time.sleep(wait)

        if problem == "HTTP 429":
            raise EmbeddingError(
                "Gemini's free rate limit was reached. Please try again in a few minutes."
            )
        raise EmbeddingError(f"Gemini embedding API failed ({problem}).")

    def _check_dim(self, vector: list[float]) -> list[float]:
        """Make sure Gemini returned the vector size the Redis index expects."""
        if len(vector) != self.dim:
            raise EmbeddingError(
                f"Gemini returned {len(vector)}-dim vectors, expected {self.dim}."
            )
        return vector

    def embed_documents(
        self, texts: list[str], on_rate_limit: RateLimitCallback | None = None
    ) -> list[list[float]]:
        """Embed README chunks, in batches of EMBEDDING_BATCH_SIZE."""
        vectors = []
        for start in range(0, len(texts), EMBEDDING_BATCH_SIZE):
            batch = texts[start:start + EMBEDDING_BATCH_SIZE]
            data = self._post(
                "batchEmbedContents",
                {
                    "requests": [
                        {
                            "model": self.model,
                            "content": {"parts": [{"text": text}]},
                            "taskType": "RETRIEVAL_DOCUMENT",
                            "outputDimensionality": self.dim,
                        }
                        for text in batch
                    ]
                },
                max_rate_limit_wait=INDEXING_MAX_WAIT,
                on_rate_limit=on_rate_limit,
            )
            embeddings = data.get("embeddings", [])
            if len(embeddings) != len(batch):
                raise EmbeddingError(
                    f"Gemini returned {len(embeddings)} vectors for {len(batch)} texts."
                )
            vectors.extend(self._check_dim(e["values"]) for e in embeddings)
        return vectors

    def embed_query(self, text: str) -> list[float]:
        """Embed a user's question."""
        data = self._post(
            "embedContent",
            {
                "model": self.model,
                "content": {"parts": [{"text": text}]},
                "taskType": "RETRIEVAL_QUERY",
                "outputDimensionality": self.dim,
            },
            max_rate_limit_wait=CHAT_MAX_WAIT,
        )
        return self._check_dim(data["embedding"]["values"])


_embeddings_model = None


def _get_embeddings_model() -> GeminiEmbeddings:
    """Create and cache the embedding model instance."""
    global _embeddings_model
    if _embeddings_model is None:
        _embeddings_model = GeminiEmbeddings(api_key=settings.GOOGLE_API_KEY)
    return _embeddings_model


def _vector_to_bytes(vector: list[float]) -> bytes:
    """
    Convert a list of floats to bytes for Redis storage.

    Redis stores vectors as raw bytes (32-bit floats).
    """
    return np.array(vector, dtype=np.float32).tobytes()


# ── Index Management ─────────────────────────────────────────────────


def _create_index_if_not_exists() -> None:
    """
    Create the RediSearch vector index if it doesn't already exist.
    If the index exists but has a different dimension, recreate it.
    """
    try:
        info = redis_client_raw.ft(INDEX_NAME).info()
    except ResponseError:
        info = None  # Index doesn't exist yet

    if info is not None:
        current_dim = None
        for attr in info.get("attributes", []):
            attr_strs = [
                x.decode("utf-8") if isinstance(x, bytes) else str(x)
                for x in attr
            ]
            if "embedding" in attr_strs and "dim" in attr_strs:
                try:
                    current_dim = int(attr[attr_strs.index("dim") + 1])
                except (ValueError, IndexError):
                    pass
                break

        if current_dim is None or current_dim == EMBEDDING_DIM:
            return  # Index exists and dimension matches

        logger.warning(
            f"Dimension mismatch in Redis index "
            f"(found {current_dim}, expected {EMBEDDING_DIM}). Recreating index..."
        )
        redis_client_raw.ft(INDEX_NAME).dropindex(delete_documents=True)

    schema = (
        TextField("content"),
        TagField("username"),
        TagField("repo_name"),
        VectorField(
            "embedding",
            "FLAT",
            {
                "TYPE": "FLOAT32",
                "DIM": EMBEDDING_DIM,
                "DISTANCE_METRIC": "COSINE",
            },
        ),
    )

    definition = IndexDefinition(
        prefix=[DOC_PREFIX],
        index_type=IndexType.HASH,
    )

    redis_client_raw.ft(INDEX_NAME).create_index(
        fields=schema,
        definition=definition,
    )
    logger.info(f"Created RediSearch index '{INDEX_NAME}' (dim={EMBEDDING_DIM})")


def _escape_tag(value: str) -> str:
    """Escape characters that have a meaning inside a RediSearch tag query."""
    return re.sub(r"([,./\-+*?^$()[\]{}|\\:!@#%&=<>~\"' ])", r"\\\1", value)


# ── SHA Cache ────────────────────────────────────────────────────────


def _get_repo_cache_key(username: str, repo_name: str) -> str:
    """Build the Redis key for a repo's embedding cache."""
    return f"{CACHE_PREFIX}{username}:{repo_name}"


def _get_cached_sha(username: str, repo_name: str) -> str | None:
    """
    Check if a repo's README has already been embedded.

    Returns the cached SHA if it exists, otherwise None.
    """
    cached = redis_client.get(_get_repo_cache_key(username, repo_name))
    if cached:
        try:
            return json.loads(cached).get("sha")
        except ValueError:
            return None
    return None


def _set_repo_cache(
    username: str, repo_name: str, sha: str, chunk_count: int
) -> None:
    """Store the SHA and chunk count for a repo's embedded README."""
    redis_client.set(
        _get_repo_cache_key(username, repo_name),
        json.dumps(
            {
                "sha": sha,
                "chunk_count": chunk_count,
                "timestamp": time.time(),
            }
        ),
        ex=DATA_TTL_SECONDS,
    )


# ── Old Vector Cleanup ───────────────────────────────────────────────


def _scan(pattern: str):
    """
    Iterate over keys matching a pattern.

    SCAN walks the keyspace in small steps. KEYS would do it in one
    blocking call, and Redis is single-threaded, so KEYS freezes every
    other request while it runs.
    """
    return redis_client_raw.scan_iter(match=pattern, count=500)


def _delete_repo_vectors(username: str, repo_name: str) -> int:
    """
    Delete all existing vectors for a specific repo.

    This prevents stale chunks from staying behind when a README
    gets shorter. Returns the number of keys deleted.
    """
    keys = list(_scan(f"{DOC_PREFIX}{username}:{repo_name}:*"))
    if keys:
        redis_client_raw.delete(*keys)
    return len(keys)


def _refresh_and_prune(username: str, keep_repos: set[str]) -> int:
    """
    Run once a profile has been indexed:
    - Delete vectors and cache entries for repos that are no longer indexed
      (dropped out of the top N, README deleted or shortened, repo removed).
    - Reset the expiry on everything else, so the whole profile lives
      for another DATA_TTL_SECONDS from now.

    Key formats:
        doc:readme:{username}:{repo}:{i}   → repo is part [3]
        cache:embed:{username}:{repo}      → repo is part [3]

    Returns the number of keys deleted.
    """
    deleted = 0
    pipe = redis_client_raw.pipeline(transaction=False)

    for pattern in (f"{DOC_PREFIX}{username}:*", f"{CACHE_PREFIX}{username}:*"):
        for key in _scan(pattern):
            repo_name = key.decode("utf-8").split(":")[3]
            if repo_name in keep_repos:
                pipe.expire(key, DATA_TTL_SECONDS)
            else:
                pipe.delete(key)
                deleted += 1

    pipe.execute()
    return deleted


# ── Store Embeddings (Per-Repo Streaming) ────────────────────────────


def embed_and_store(
    username: str,
    repositories: list[dict],
    progress_callback=None,
) -> dict:
    """
    Process GitHub repositories and store their README embeddings in Redis.

    Optimized pipeline:
    - Processes repos one at a time (low memory)
    - Checks SHA cache to skip unchanged repos
    - Batches embedding API calls
    - Replaces a repo's old vectors only after new ones were created
    - Removes repos that are no longer indexed, refreshes expiry on the rest
    - Reports granular progress via callback

    Args:
        username: GitHub username (stored as metadata for filtering)
        repositories: List of repo dicts from github_service.analyze_profile()
                     Each repo should have: name, readme, readme_sha
        progress_callback: Optional callable(phase, detail_dict) for progress

    Returns:
        dict: {
            "total_chunks": int,
            "repos_embedded": int,
            "repos_cached": int,
            "repos_skipped": int,
        }
    """
    # Step 1: Ensure the index exists
    log_to_redis(username, "Step 1: checking/creating search index...")
    _create_index_if_not_exists()

    stats = {
        "total_chunks": 0,
        "repos_embedded": 0,
        "repos_cached": 0,
        "repos_skipped": 0,
    }

    # Filter to repos that have README content
    indexable_repos = [
        r for r in repositories if r.get("readme") and r["readme"].strip()
    ]
    log_to_redis(username, f"Found {len(indexable_repos)} repos with indexable READMEs.")

    total_repos = len(indexable_repos)
    embeddings_model = _get_embeddings_model() if indexable_repos else None

    # Step 2: Process each repo individually (streaming)
    for repo_idx, repo in enumerate(indexable_repos):
        repo_name = repo["name"]
        readme = repo["readme"]
        readme_sha = repo.get("readme_sha")
        step = f"[{repo_idx + 1}/{total_repos}] {repo_name}"

        # ── Cache Check ──────────────────────────────────────────
        # Same README SHA as last time, and its first chunk is still in
        # Redis → nothing changed, skip the embedding API entirely.
        if readme_sha and _get_cached_sha(username, repo_name) == readme_sha:
            if redis_client_raw.exists(f"{DOC_PREFIX}{username}:{repo_name}:0"):
                stats["repos_cached"] += 1
                log_to_redis(username, f"{step}: cache HIT (README unchanged), skipping.")
                if progress_callback:
                    progress_callback(
                        "embedding",
                        {
                            "current_repo": repo_name,
                            "repos_done": repo_idx + 1,
                            "repos_total": total_repos,
                            "chunks_done": stats["total_chunks"],
                            "detail": "cached",
                        },
                    )
                continue

        # ── Chunk ────────────────────────────────────────────────
        chunks = _split_text(readme)

        if not chunks:
            stats["repos_skipped"] += 1
            log_to_redis(username, f"{step}: no text chunks, skipping.")
            continue

        if progress_callback:
            progress_callback(
                "embedding",
                {
                    "current_repo": repo_name,
                    "repos_done": repo_idx,
                    "repos_total": total_repos,
                    "chunks_done": stats["total_chunks"],
                    "detail": f"embedding {len(chunks)} chunks",
                },
            )

        # ── Embed ────────────────────────────────────────────────
        # The repo name goes in front of each chunk so the vector also
        # "knows" which project the text belongs to.
        log_to_redis(username, f"{step}: embedding {len(chunks)} chunks...")

        def report_rate_limit(seconds: float) -> None:
            """
            Tell the user why the job paused. Reporting progress also
            refreshes the job's lock, so a long pause can't look like a dead job.
            """
            log_to_redis(username, f"{step}: Gemini rate limit, waiting {seconds:.0f}s.")
            if progress_callback:
                progress_callback(
                    "embedding",
                    {
                        "current_repo": repo_name,
                        "repos_done": repo_idx,
                        "repos_total": total_repos,
                        "chunks_done": stats["total_chunks"],
                        "wait_seconds": round(seconds),
                        "detail": "waiting for Gemini's rate limit",
                    },
                )

        vectors = embeddings_model.embed_documents(
            [f"Repository: {repo_name}\n\n{chunk}" for chunk in chunks],
            on_rate_limit=report_rate_limit,
        )

        # ── Replace old vectors with the new ones ────────────────
        deleted = _delete_repo_vectors(username, repo_name)
        if deleted:
            log_to_redis(username, f"{step}: deleted {deleted} old chunks.")

        pipeline = redis_client_raw.pipeline(transaction=False)
        for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
            key = f"{DOC_PREFIX}{username}:{repo_name}:{i}"
            pipeline.hset(
                key,
                mapping={
                    "content": chunk,
                    "username": username,
                    "repo_name": repo_name,
                    "embedding": _vector_to_bytes(vector),
                },
            )
            pipeline.expire(key, DATA_TTL_SECONDS)
            if (i + 1) % REDIS_PIPELINE_BATCH == 0:
                pipeline.execute()
                pipeline = redis_client_raw.pipeline(transaction=False)

        pipeline.execute()  # Flush remaining
        log_to_redis(username, f"{step}: stored {len(chunks)} chunks.")

        # ── Update cache ─────────────────────────────────────────
        if readme_sha:
            _set_repo_cache(username, repo_name, readme_sha, len(chunks))

        stats["total_chunks"] += len(chunks)
        stats["repos_embedded"] += 1

    # Step 3: Drop repos that are no longer indexed, refresh expiry on the rest
    removed = _refresh_and_prune(username, {r["name"] for r in indexable_repos})
    if removed:
        log_to_redis(username, f"Removed {removed} keys of repos that are no longer indexed.")

    log_to_redis(username, f"All repositories processed. New chunks: {stats['total_chunks']}.")
    if progress_callback:
        progress_callback(
            "saving",
            {
                "repos_done": total_repos,
                "repos_total": total_repos,
                "chunks_done": stats["total_chunks"],
                "detail": "complete",
            },
        )

    logger.info(
        f"Indexing complete for '{username}': {stats['repos_embedded']} embedded, "
        f"{stats['repos_cached']} cached, {stats['repos_skipped']} skipped, "
        f"{stats['total_chunks']} new chunks."
    )

    return stats


# ── Search ───────────────────────────────────────────────────────────


def count_chunks(username: str) -> int:
    """
    How many README chunks are stored for this user.

    Used before a chat question so we don't pay for an embedding call
    when there is nothing to search.
    """
    _create_index_if_not_exists()
    query = Query(f"@username:{{{_escape_tag(username)}}}").paging(0, 0).dialect(2)
    return redis_client_raw.ft(INDEX_NAME).search(query).total


def search_similar(
    query: str, username: str, top_k: int = TOP_K
) -> list[dict]:
    """
    Find the most similar README chunks to a query using vector search.

    Steps:
    1. Convert query text → embedding vector
    2. Run Redis vector similarity search (KNN)
    3. Return top_k most similar chunks with metadata

    The Redis query uses:
    - KNN (K-Nearest Neighbors): find the K closest vectors
    - @username filter: only search this user's repos
    - COSINE distance: lower = more similar

    Returns:
        List of dicts with content, repo_name, and score
    """

    # Step 1: Ensure index exists
    _create_index_if_not_exists()

    # Step 2: Convert query to embedding vector
    query_vector = _get_embeddings_model().embed_query(query)
    query_bytes = _vector_to_bytes(query_vector)

    # Step 3: Build and run the Redis vector search query
    redis_query = (
        Query(
            f"(@username:{{{_escape_tag(username)}}})=>"
            f"[KNN {top_k} @embedding $vec AS score]"
        )
        .sort_by("score")
        .return_fields("content", "repo_name", "score")
        .dialect(2)
    )

    results = redis_client_raw.ft(INDEX_NAME).search(
        redis_query,
        query_params={"vec": query_bytes},
    )

    # Step 4: Format results
    documents = []
    for doc in results.docs:
        content = doc.content
        repo_name = doc.repo_name
        score = doc.score

        if isinstance(content, bytes):
            content = content.decode("utf-8")
        if isinstance(repo_name, bytes):
            repo_name = repo_name.decode("utf-8")
        if isinstance(score, bytes):
            score = score.decode("utf-8")

        documents.append(
            {
                "content": content,
                "repo_name": repo_name,
                "score": float(score),
            }
        )

    return documents
