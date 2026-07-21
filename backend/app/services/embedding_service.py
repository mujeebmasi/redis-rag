"""
Embedding Service
=================
The core of the RAG pipeline — converts text into vectors and stores them in Redis.

What is an Embedding?
- A list of numbers (e.g., [0.1, -0.3, 0.7, ...]) that represents the *meaning* of text
- Similar text → similar numbers → found by vector search
- This is how "semantic search" works (searching by meaning, not keywords)

Pipeline:
1. Take README text from GitHub repos
2. Split into smaller chunks (LLMs have context limits)
3. Convert each chunk into an embedding vector
4. Store vectors in Redis Vector Database

How Redis Vector Search Works (under the hood):
- We create a RediSearch index with a VECTOR field
- Each document is stored as a Redis Hash with the vector + metadata
- When searching, Redis computes cosine similarity between query vector
  and all stored vectors, returning the most similar ones
- This is FAST — Redis does it in-memory

Note: We use redis-py directly instead of langchain-redis to avoid
dependency conflicts with Python 3.14 and to show you how vector
search actually works at the Redis level.
"""

import json
import os
import httpx
import re
import struct
import numpy as np
import time
import random
from redis.commands.search.field import TextField, TagField, VectorField
from redis.commands.search.index_definition import IndexDefinition, IndexType
from redis.commands.search.query import Query
from app.core.config import settings
from app.core.redis_client import redis_client_raw

# ── Constants ────────────────────────────────────────────────────────

INDEX_NAME = "idx:github_readmes"     # RediSearch index name
DOC_PREFIX = "doc:readme:"            # Key prefix for stored documents

_text_splitter = None

def _get_text_splitter():
    global _text_splitter
    if _text_splitter is None:
        from langchain_text_splitters import RecursiveCharacterTextSplitter
        _text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
        )
    return _text_splitter


# ── Embedding Model ─────────────────────────────────────────────────
# Converts text into vectors using a HuggingFace embedding model.
# Defaults to sentence-transformers/all-MiniLM-L6-v2 (384 dimensions).

class HuggingFaceAPIEmbeddings:
    def __init__(self, model_name: str, hf_token: str | None = None):
        self.model_name = model_name
        self.hf_token = hf_token
        self.api_url = f"https://router.huggingface.co/hf-inference/models/{model_name}/pipeline/feature-extraction"

    def _embed(self, texts: list[str]) -> list[list[float]]:
        headers = {}
        if self.hf_token:
            headers["Authorization"] = f"Bearer {self.hf_token}"
        try:
            response = httpx.post(
                self.api_url,
                headers=headers,
                json={"inputs": texts, "options": {"wait_for_model": True}},
                timeout=30.0
            )
            response.raise_for_status()
            result = response.json()
            if isinstance(result, list) and len(result) > 0:
                return result
            raise ValueError(f"Unexpected API response: {result}")
        except Exception as e:
            raise RuntimeError(f"HuggingFace Inference API error: {str(e)}")

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text])[0]


_embeddings_model = None


def _get_embeddings_model():
    """Create and cache the HuggingFace embedding model instance."""
    global _embeddings_model
    if _embeddings_model is None:
        token = settings.HUGGINGFACEHUB_API_TOKEN or settings.HF_TOKEN
        if os.getenv("RENDER") == "true" or token:
            _embeddings_model = HuggingFaceAPIEmbeddings(
                model_name=settings.HF_EMBEDDING_MODEL,
                hf_token=token,
            )
        else:
            from langchain_huggingface import HuggingFaceEmbeddings
            _embeddings_model = HuggingFaceEmbeddings(
                model_name=settings.HF_EMBEDDING_MODEL,
                model_kwargs={"device": "cpu"},
            )
    return _embeddings_model


def _get_vector_dim() -> int:
    """Gets the embedding vector dimension dynamically."""
    model = _get_embeddings_model()
    try:
        # Standard sentence-transformers client method
        return model.client.get_sentence_embedding_dimension()
    except Exception:
        # Fallback by embedding a test query
        return len(model.embed_query("test"))


def _vector_to_bytes(vector: list[float]) -> bytes:
    """
    Convert a list of floats to bytes for Redis storage.
    
    Redis stores vectors as raw bytes (32-bit floats).
    struct.pack converts Python floats → C-style binary format.
    """
    return np.array(vector, dtype=np.float32).tobytes()


# ── Index Management ─────────────────────────────────────────────────


def _create_index_if_not_exists() -> None:
    """
    Create the RediSearch vector index if it doesn't already exist.
    If the index exists but has a different dimension, recreate it.
    
    The index defines:
    - content (TEXT): the actual text chunk (searchable by keywords too)
    - username (TAG): GitHub username (for filtering by user)
    - repo_name (TAG): repository name (for filtering by repo)
    - embedding (VECTOR): the embedding vector (for similarity search)
    
    FLAT algorithm: brute-force search (fine for < 100K vectors)
    COSINE distance: measures angle between vectors (standard for text)
    """
    vector_dim = _get_vector_dim()
    try:
        info = redis_client_raw.ft(INDEX_NAME).info()
        # Check current index dimension to handle model swaps seamlessly
        attributes = info.get("attributes", [])
        current_dim = None
        for attr in attributes:
            attr_strs = [x.decode("utf-8") if isinstance(x, bytes) else str(x) for x in attr]
            if "embedding" in attr_strs and "dim" in attr_strs:
                try:
                    dim_idx = attr_strs.index("dim")
                    current_dim = int(attr[dim_idx + 1])
                except (ValueError, IndexError):
                    pass
                break
        
        if current_dim is not None and current_dim != vector_dim:
            print(f"Dimension mismatch in Redis index (found {current_dim}, expected {vector_dim}). Recreating index...")
            redis_client_raw.ft(INDEX_NAME).dropindex(delete_documents=True)
        else:
            return  # Index exists and dimension matches, nothing to do

    except Exception:
        # Index doesn't exist — create it
        pass

    # Define the index schema
    schema = (
        TextField("content"),
        TagField("username"),
        TagField("repo_name"),
        VectorField(
            "embedding",
            "FLAT",                      # Algorithm: FLAT = brute force (simple, accurate)
            {
                "TYPE": "FLOAT32",       # 32-bit floating point
                "DIM": vector_dim,       # dimensions dynamically fetched
                "DISTANCE_METRIC": "COSINE",  # Cosine similarity
            },
        ),
    )

    # Create the index on all keys starting with DOC_PREFIX
    definition = IndexDefinition(
        prefix=[DOC_PREFIX],
        index_type=IndexType.HASH,
    )

    redis_client_raw.ft(INDEX_NAME).create_index(
        fields=schema,
        definition=definition,
    )


# ── Store Embeddings ─────────────────────────────────────────────────


def embed_and_store(username: str, repositories: list[dict]) -> int:
    """
    Process GitHub repositories and store their README embeddings in Redis.
    
    Steps:
    1. Create the RediSearch index (if it doesn't exist)
    2. Filter repos that have README content
    3. Split each README into chunks
    4. Generate embedding vectors for all chunks
    5. Store each chunk as a Redis Hash with vector + metadata
    
    Args:
        username: GitHub username (stored as metadata for filtering)
        repositories: List of repo dicts from github_service.analyze_profile()
                     Each repo should have: name, readme (str or None)
    
    Returns:
        int: Number of chunks stored in Redis
    """

    # Step 1: Ensure the index exists
    _create_index_if_not_exists()

    # Step 2-3: Collect all chunks with metadata
    chunks = []       # The text content
    metadata = []     # Associated metadata (username, repo_name)

    for repo in repositories:
        readme = repo.get("readme")

        # Skip repos without README
        if not readme or not readme.strip():
            continue

        # Split README into chunks
        repo_chunks = _get_text_splitter().split_text(readme)

        for chunk in repo_chunks:
            chunks.append(chunk)
            metadata.append({
                "username": username,
                "repo_name": repo["name"],
            })

    if not chunks:
        print("DEBUG: No chunks generated (no READMEs found or all empty).", flush=True)
        return 0

    from concurrent.futures import ThreadPoolExecutor

    print(f"DEBUG: Chunking complete. Generated {len(chunks)} chunks from READMEs.", flush=True)
    # Step 4: Generate embeddings for all chunks in parallel batches
    BATCH_SIZE = 16
    batches = [chunks[i:i + BATCH_SIZE] for i in range(0, len(chunks), BATCH_SIZE)]

    def _embed_batch(batch_text):
        model = _get_embeddings_model()
        return model.embed_documents(batch_text)

    print(f"DEBUG: Requesting embeddings for {len(chunks)} chunks across {len(batches)} parallel batches...", flush=True)
    with ThreadPoolExecutor(max_workers=5) as executor:
        batch_results = list(executor.map(_embed_batch, batches))

    vectors = [vec for b_vecs in batch_results for vec in b_vecs]
    print(f"DEBUG: Successfully generated {len(vectors)} embedding vectors.", flush=True)

    # Step 5: Store each chunk in Redis as a Hash
    # Key format: doc:readme:{username}:{repo}:{index}
    pipeline = redis_client_raw.pipeline()

    for i, (chunk, meta, vector) in enumerate(zip(chunks, metadata, vectors)):
        key = f"{DOC_PREFIX}{meta['username']}:{meta['repo_name']}:{i}"

        pipeline.hset(
            key,
            mapping={
                "content": chunk,
                "username": meta["username"],
                "repo_name": meta["repo_name"],
                "embedding": _vector_to_bytes(vector),
            },
        )

    pipeline.execute()

    return len(chunks)


# ── Search ───────────────────────────────────────────────────────────


def search_similar(query: str, username: str, top_k: int = 5) -> list[dict]:
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
        List of dicts: [
            {
                "content": "chunk text...",
                "repo_name": "repo-name",
                "score": 0.85  (similarity score)
            },
            ...
        ]
    """

    # Step 1: Ensure index exists
    _create_index_if_not_exists()

    # Step 2: Convert query to embedding vector
    embeddings_model = _get_embeddings_model()
    query_vector = embeddings_model.embed_query(query)
    query_bytes = _vector_to_bytes(query_vector)

    # Step 3: Build and run the Redis vector search query
    # Syntax: (@username:{username})=>[KNN 5 @embedding $vec AS score]
    # This says: "filter by username, then find 5 nearest vectors, call the distance 'score'"
    # RediSearch tags require escaping of special characters like hyphens.
    # We use a single-pass regex replacement to avoid double-escaping the backslash.
    escaped_username = re.sub(r"([,./\-+*?^$()[\]{}|\\:!@#%&=<>])", r"\\\1", username)

    redis_query = (
        Query(f"(@username:{{{escaped_username}}})=>[KNN {top_k} @embedding $vec AS score]")
        .sort_by("score")
        .return_fields("content", "repo_name", "score")
        .dialect(2)  # Required for vector search
    )

    results = redis_client_raw.ft(INDEX_NAME).search(
        redis_query,
        query_params={"vec": query_bytes},
    )

    # Step 4: Format results
    # Note: redis_client_raw has decode_responses=False, so fields come back as bytes
    documents = []
    for doc in results.docs:
        content = doc.content
        repo_name = doc.repo_name
        score = doc.score

        # Decode bytes → str if needed (raw client returns bytes)
        if isinstance(content, bytes):
            content = content.decode("utf-8")
        if isinstance(repo_name, bytes):
            repo_name = repo_name.decode("utf-8")
        if isinstance(score, bytes):
            score = score.decode("utf-8")

        documents.append({
            "content": content,
            "repo_name": repo_name,
            "score": float(score),
        })

    return documents
