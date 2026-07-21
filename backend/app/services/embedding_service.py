"""
Embedding Service
=================
The core of the RAG pipeline — converts text into vectors and stores them in Redis.

What is an Embedding?
- A list of numbers (e.g., [0.1, -0.3, 0.7, ...]) that represents the *meaning* of text
- Similar text → similar numbers → found by vector search
- This is how "semantic search" works (searching by meaning, not keywords)

Pipeline (optimized):
1. For each repository:
   a. Check SHA cache — skip if README hasn't changed
   b. Clean old vectors for this repo
   c. Chunk the README text
   d. Generate embedding vectors (batched, with retry)
   e. Store vectors in Redis
   f. Update SHA cache
   g. Report progress

This per-repo streaming approach keeps peak memory low and enables
granular progress reporting.

Note: We use redis-py directly instead of langchain-redis to avoid
dependency conflicts with Python 3.14 and to show you how vector
search actually works at the Redis level.
"""

import json
import logging
import os
import re
import time

import httpx
import numpy as np
from redis.commands.search.field import TagField, TextField, VectorField
from redis.commands.search.index_definition import IndexDefinition, IndexType
from redis.commands.search.query import Query

from app.core.config import settings
from app.core.indexing_config import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    EMBEDDING_API_TIMEOUT,
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_MAX_RETRIES,
    EMBEDDING_MAX_WORKERS,
    REDIS_PIPELINE_BATCH,
    REPO_CACHE_TTL_SECONDS,
    SINGLE_USER_MODE,
)
from app.core.redis_client import redis_client, redis_client_raw

logger = logging.getLogger(__name__)

# ── Constants ────────────────────────────────────────────────────────

INDEX_NAME = "idx:github_readmes"  # RediSearch index name
DOC_PREFIX = "doc:readme:"  # Key prefix for stored documents
CACHE_PREFIX = "cache:embed:"  # Key prefix for SHA cache


def log_to_redis(username: str, message: str) -> None:
    """Helper to write log messages to a Redis list for remote debugging."""
    try:
        key = f"logs:analyze:{username.lower().strip()}"
        redis_client.rpush(key, f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}")
        redis_client.expire(key, 3600)
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


def _get_text_splitter():
    """Returns the fast built-in text splitter (kept for API compatibility)."""
    return type('_Splitter', (), {'split_text': staticmethod(_split_text)})()


# ── Embedding Model ─────────────────────────────────────────────────


class HuggingFaceAPIEmbeddings:
    """
    Embedding model that calls the HuggingFace Inference API.

    Includes exponential backoff retry for transient failures
    (503 model loading, 429 rate limit, timeouts).
    """

    def __init__(self, model_name: str, hf_token: str | None = None):
        self.model_name = model_name
        self.hf_token = hf_token
        self.api_url = (
            f"https://router.huggingface.co/hf-inference/models/"
            f"{model_name}/pipeline/feature-extraction"
        )

    def _embed_with_retry(self, texts: list[str]) -> list[list[float]]:
        """
        Call the HuggingFace API with exponential backoff retry.

        Retries on:
        - 503 Service Unavailable (model loading)
        - 429 Too Many Requests (rate limited)
        - Timeouts
        - Connection errors
        """
        headers = {}
        if self.hf_token:
            headers["Authorization"] = f"Bearer {self.hf_token}"

        last_error = None
        for attempt in range(1, EMBEDDING_MAX_RETRIES + 1):
            try:
                response = httpx.post(
                    self.api_url,
                    headers=headers,
                    json={
                        "inputs": texts,
                        "options": {"wait_for_model": True},
                    },
                    timeout=EMBEDDING_API_TIMEOUT,
                )
                response.raise_for_status()
                result = response.json()
                if isinstance(result, list) and len(result) > 0:
                    return result
                raise ValueError(f"Unexpected API response: {result}")

            except (
                httpx.HTTPStatusError,
                httpx.TimeoutException,
                httpx.ConnectError,
            ) as e:
                last_error = e
                # Only retry on transient errors
                if isinstance(e, httpx.HTTPStatusError):
                    if e.response.status_code not in (429, 503):
                        raise  # Non-retryable error

                wait = 2**attempt  # 2s, 4s, 8s
                logger.warning(
                    f"Embedding API attempt {attempt}/{EMBEDDING_MAX_RETRIES} "
                    f"failed: {e}. Retrying in {wait}s..."
                )
                time.sleep(wait)

            except Exception as e:
                raise RuntimeError(
                    f"HuggingFace Inference API error: {str(e)}"
                )

        raise RuntimeError(
            f"Embedding API failed after {EMBEDDING_MAX_RETRIES} retries: "
            f"{last_error}"
        )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of documents with retry logic."""
        return self._embed_with_retry(texts)

    def embed_query(self, text: str) -> list[float]:
        """Embed a single query string with retry logic."""
        return self._embed_with_retry([text])[0]


class GeminiAPIEmbeddings:
    """
    Lightweight Gemini API client that bypasses the Google GenAI SDK.

    This completely prevents Google's GCP default credentials lookup,
    which deadlocks on non-GCP cloud platforms like Render.
    """

    def __init__(self, google_api_key: str, model_name: str = "models/gemini-embedding-001"):
        self.google_api_key = google_api_key
        self.model_name = model_name
        self.single_url = f"https://generativelanguage.googleapis.com/v1beta/{model_name}:embedContent?key={google_api_key}"
        self.batch_url = f"https://generativelanguage.googleapis.com/v1beta/{model_name}:batchEmbedContents?key={google_api_key}"

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        requests = [
            {
                "model": self.model_name,
                "content": {"parts": [{"text": t}]}
            }
            for t in texts
        ]

        try:
            response = httpx.post(
                self.batch_url,
                json={"requests": requests},
                timeout=30.0
            )
            response.raise_for_status()
            data = response.json()
            embeddings = data.get("embeddings", [])
            return [e["values"] for e in embeddings]
        except Exception as e:
            raise RuntimeError(f"Gemini API Batch Embedding error: {str(e)}")

    def embed_query(self, text: str) -> list[float]:
        try:
            response = httpx.post(
                self.single_url,
                json={"content": {"parts": [{"text": text}]}},
                timeout=30.0
            )
            response.raise_for_status()
            data = response.json()
            return data["embedding"]["values"]
        except Exception as e:
            raise RuntimeError(f"Gemini API Embedding error: {str(e)}")


_embeddings_model = None


def _get_embeddings_model():
    """Create and cache the embedding model instance."""
    global _embeddings_model
    if _embeddings_model is None:
        # Default to Google Gemini Embeddings (ultra-fast, 3072 dims, no cold starts)
        # Fall back to local CPU model ONLY if LOCAL_EMBEDDING=true is set.
        if os.getenv("LOCAL_EMBEDDING") == "true":
            logger.info("LOCAL_EMBEDDING is true. Initializing heavy local HuggingFace embeddings on CPU...")
            from langchain_huggingface import HuggingFaceEmbeddings

            _embeddings_model = HuggingFaceEmbeddings(
                model_name=settings.HF_EMBEDDING_MODEL,
                model_kwargs={"device": "cpu"},
            )
        else:
            logger.info("Using ultra-fast Google Gemini REST Embeddings (models/gemini-embedding-001).")
            _embeddings_model = GeminiAPIEmbeddings(
                google_api_key=settings.GOOGLE_API_KEY,
                model_name="models/gemini-embedding-001",
            )
    return _embeddings_model


def _get_vector_dim() -> int:
    """Gets the embedding vector dimension dynamically."""
    model = _get_embeddings_model()
    try:
        return model.client.get_sentence_embedding_dimension()
    except Exception:
        return len(model.embed_query("test"))


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
    vector_dim = _get_vector_dim()
    try:
        info = redis_client_raw.ft(INDEX_NAME).info()
        attributes = info.get("attributes", [])
        current_dim = None
        for attr in attributes:
            attr_strs = [
                x.decode("utf-8") if isinstance(x, bytes) else str(x)
                for x in attr
            ]
            if "embedding" in attr_strs and "dim" in attr_strs:
                try:
                    dim_idx = attr_strs.index("dim")
                    current_dim = int(attr[dim_idx + 1])
                except (ValueError, IndexError):
                    pass
                break

        if current_dim is not None and current_dim != vector_dim:
            logger.warning(
                f"Dimension mismatch in Redis index "
                f"(found {current_dim}, expected {vector_dim}). "
                f"Recreating index..."
            )
            redis_client_raw.ft(INDEX_NAME).dropindex(delete_documents=True)
        else:
            return  # Index exists and dimension matches

    except Exception:
        pass  # Index doesn't exist — create it

    schema = (
        TextField("content"),
        TagField("username"),
        TagField("repo_name"),
        VectorField(
            "embedding",
            "FLAT",
            {
                "TYPE": "FLOAT32",
                "DIM": vector_dim,
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
    logger.info(f"Created RediSearch index '{INDEX_NAME}' (dim={vector_dim})")


# ── SHA Cache ────────────────────────────────────────────────────────


def _get_repo_cache_key(username: str, repo_name: str) -> str:
    """Build the Redis key for a repo's embedding cache."""
    return f"{CACHE_PREFIX}{username}:{repo_name}"


def _get_cached_sha(username: str, repo_name: str) -> str | None:
    """
    Check if a repo's README has already been embedded.

    Returns the cached SHA if it exists, otherwise None.
    """
    try:
        cached = redis_client.get(_get_repo_cache_key(username, repo_name))
        if cached:
            data = json.loads(cached)
            return data.get("sha")
    except Exception:
        pass
    return None


def _set_repo_cache(
    username: str, repo_name: str, sha: str, chunk_count: int
) -> None:
    """Store the SHA and chunk count for a repo's embedded README."""
    try:
        redis_client.set(
            _get_repo_cache_key(username, repo_name),
            json.dumps(
                {
                    "sha": sha,
                    "chunk_count": chunk_count,
                    "timestamp": time.time(),
                }
            ),
            ex=REPO_CACHE_TTL_SECONDS,
        )
    except Exception as e:
        logger.warning(f"Failed to set cache for {repo_name}: {e}")


# ── Old Vector Cleanup ───────────────────────────────────────────────


def _delete_repo_vectors(username: str, repo_name: str) -> int:
    """
    Delete all existing vectors for a specific repo.

    This prevents stale vectors from accumulating when READMEs change.
    Returns the number of keys deleted.
    """
    pattern = f"{DOC_PREFIX}{username}:{repo_name}:*"
    keys = redis_client_raw.keys(pattern)
    if keys:
        redis_client_raw.delete(*keys)
    return len(keys)


def cleanup_other_users_data(active_username: str) -> int:
    """
    Deletes all vectors, SHA caches, and analysis statuses for all users
    OTHER than the current active_username.

    This keeps the Redis database footprint extremely small.
    """
    # 1. Clear other users' documents
    # Find all keys starting with doc:readme:
    all_doc_keys = redis_client_raw.keys(f"{DOC_PREFIX}*")
    keys_to_delete = []
    for key in all_doc_keys:
        try:
            key_str = key.decode("utf-8")
            # Key format: doc:readme:{username}:{repo}:{index}
            parts = key_str.split(":")
            if len(parts) >= 4:
                username = parts[2]
                if username.lower() != active_username.lower():
                    keys_to_delete.append(key)
        except Exception:
            pass

    # 2. Clear other users' cache keys and status keys
    all_cache_keys = redis_client.keys(f"{CACHE_PREFIX}*")
    for key in all_cache_keys:
        # Key format: cache:embed:{username}:{repo}
        parts = key.split(":")
        if len(parts) >= 3:
            username = parts[2]
            if username.lower() != active_username.lower():
                keys_to_delete.append(key)

    all_status_keys = redis_client.keys("status:analyze:*")
    for key in all_status_keys:
        # Key format: status:analyze:{username}
        parts = key.split(":")
        if len(parts) >= 3:
            username = parts[2]
            if username.lower() != active_username.lower():
                keys_to_delete.append(key)

    if keys_to_delete:
        # Both client connection formats connect to the same Redis instance
        redis_client_raw.delete(*keys_to_delete)
        logger.info(
            f"Single-User Mode: Cleaned up {len(keys_to_delete)} Redis keys "
            f"for other users."
        )
        return len(keys_to_delete)
    return 0


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
    - Cleans old vectors before re-embedding
    - Batches embedding API calls
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
    from concurrent.futures import ThreadPoolExecutor

    # Optional automatic vector garbage collection
    if SINGLE_USER_MODE:
        log_to_redis(username, f"Single-User Mode: starting cleanup of other users...")
        cleanup_other_users_data(username)
        log_to_redis(username, f"Cleanup complete.")

    # Step 1: Ensure the index exists
    log_to_redis(username, f"Step 1: checking/recreating search index...")
    _create_index_if_not_exists()
    log_to_redis(username, f"Search index is ready.")

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

    if not indexable_repos:
        log_to_redis(username, "No indexable READMEs found. Indexing aborted.")
        logger.info("No indexable READMEs found.")
        return stats

    log_to_redis(username, f"Found {len(indexable_repos)} repos with indexable READMEs.")
    embeddings_model = _get_embeddings_model()
    total_repos = len(indexable_repos)

    # Step 2: Process each repo individually (streaming)
    for repo_idx, repo in enumerate(indexable_repos):
        repo_name = repo["name"]
        readme = repo["readme"]
        readme_sha = repo.get("readme_sha")

        log_to_redis(username, f"[{repo_idx + 1}/{total_repos}] Processing repository: {repo_name}")

        # ── Cache Check ──────────────────────────────────────────
        if readme_sha:
            cached_sha = _get_cached_sha(username, repo_name)
            if cached_sha == readme_sha:
                stats["repos_cached"] += 1
                log_to_redis(username, f"[{repo_idx + 1}/{total_repos}] {repo_name}: Cache HIT (SHA unchanged). Skipping embedding.")
                logger.info(
                    f"[{repo_idx + 1}/{total_repos}] {repo_name}: "
                    f"cache hit (SHA unchanged), skipping."
                )
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
        chunks = _get_text_splitter().split_text(readme)

        if not chunks:
            stats["repos_skipped"] += 1
            log_to_redis(username, f"[{repo_idx + 1}/{total_repos}] {repo_name}: No text chunks generated. Skipping.")
            continue

        log_to_redis(username, f"[{repo_idx + 1}/{total_repos}] {repo_name}: Split into {len(chunks)} chunks.")

        print(
            f"[{repo_idx + 1}/{total_repos}] {repo_name}: "
            f"{len(chunks)} chunks to embed.",
            flush=True
        )

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

        # ── Clean old vectors ────────────────────────────────────
        deleted = _delete_repo_vectors(username, repo_name)
        if deleted:
            log_to_redis(username, f"[{repo_idx + 1}/{total_repos}] {repo_name}: Deleted {deleted} stale vectors.")
            print(f"Cleaned {deleted} old vectors for {repo_name}.", flush=True)

        # ── Embed (direct API batching) ─────────────────────────
        log_to_redis(username, f"[{repo_idx + 1}/{total_repos}] {repo_name}: Sending {len(chunks)} chunks to Gemini embedding API...")
        try:
            vectors = embeddings_model.embed_documents(chunks)
            log_to_redis(username, f"[{repo_idx + 1}/{total_repos}] {repo_name}: Received embedding vectors successfully (dim={len(vectors[0]) if vectors else 0}).")
        except Exception as embed_err:
            log_to_redis(username, f"[{repo_idx + 1}/{total_repos}] {repo_name}: ERROR in embedding API: {embed_err}")
            print(f"ERROR: Failed to embed chunks for {repo_name}: {embed_err}", flush=True)
            raise embed_err

        # ── Store in Redis ───────────────────────────────────────
        log_to_redis(username, f"[{repo_idx + 1}/{total_repos}] {repo_name}: Writing vectors to Redis...")
        pipeline = redis_client_raw.pipeline()
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
            if (i + 1) % REDIS_PIPELINE_BATCH == 0:
                pipeline.execute()
                pipeline = redis_client_raw.pipeline()

        pipeline.execute()  # Flush remaining
        log_to_redis(username, f"[{repo_idx + 1}/{total_repos}] {repo_name}: Finished storing vectors.")

        # ── Update cache ─────────────────────────────────────────
        if readme_sha:
            _set_repo_cache(username, repo_name, readme_sha, len(chunks))

        stats["total_chunks"] += len(chunks)
        stats["repos_embedded"] += 1

        print(
            f"[{repo_idx + 1}/{total_repos}] {repo_name}: "
            f"stored {len(chunks)} chunks.",
            flush=True
        )

    log_to_redis(username, f"All repositories processed. Total chunks: {stats['total_chunks']}.")
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
        f"Indexing complete: {stats['repos_embedded']} embedded, "
        f"{stats['repos_cached']} cached, "
        f"{stats['repos_skipped']} skipped, "
        f"{stats['total_chunks']} total chunks."
    )

    return stats


# ── Search ───────────────────────────────────────────────────────────


def search_similar(
    query: str, username: str, top_k: int = 5
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

    Args:
        query: The search query (natural language)
        username: GitHub username to filter by
        top_k: Number of results to return

    Returns:
        List of dicts with content, repo_name, and score
    """

    # Step 1: Ensure index exists
    _create_index_if_not_exists()

    # Step 2: Convert query to embedding vector
    embeddings_model = _get_embeddings_model()
    query_vector = embeddings_model.embed_query(query)
    query_bytes = _vector_to_bytes(query_vector)

    # Step 3: Build and run the Redis vector search query
    escaped_username = re.sub(
        r"([,./\-+*?^$()[\]{}|\\:!@#%&=<>])", r"\\\1", username
    )

    redis_query = (
        Query(
            f"(@username:{{{escaped_username}}})=>"
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
