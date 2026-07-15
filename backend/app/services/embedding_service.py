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
import struct
import numpy as np
from redis.commands.search.field import TextField, TagField, VectorField
from redis.commands.search.index_definition import IndexDefinition, IndexType
from redis.commands.search.query import Query
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings

from app.core.config import settings
from app.core.redis_client import redis_client_raw

# ── Constants ────────────────────────────────────────────────────────

INDEX_NAME = "idx:github_readmes"     # RediSearch index name
DOC_PREFIX = "doc:readme:"            # Key prefix for stored documents
VECTOR_DIM = 3072                     # Dimensions of gemini-embedding-001

# ── Text Splitter ────────────────────────────────────────────────────
# Splits large README files into smaller, overlapping chunks.
#
# Why chunk?
# - Embedding models have token limits
# - Smaller chunks = more precise search results
# - Overlap ensures we don't cut sentences in half
#
# chunk_size: max characters per chunk (1000 ≈ ~250 words)
# chunk_overlap: characters shared between consecutive chunks

text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=200,
)


# ── Embedding Model ─────────────────────────────────────────────────
# Converts text into 768-dimensional vectors using Google's embedding model.
# Free tier: 1,500 requests/minute (plenty for this project).


def _get_embeddings_model() -> GoogleGenerativeAIEmbeddings:
    """Create the embedding model instance."""
    return GoogleGenerativeAIEmbeddings(
        model="models/gemini-embedding-001",
        google_api_key=settings.GOOGLE_API_KEY,
    )


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
    
    The index defines:
    - content (TEXT): the actual text chunk (searchable by keywords too)
    - username (TAG): GitHub username (for filtering by user)
    - repo_name (TAG): repository name (for filtering by repo)
    - embedding (VECTOR): the 768-dim embedding vector (for similarity search)
    
    FLAT algorithm: brute-force search (fine for < 100K vectors)
    COSINE distance: measures angle between vectors (standard for text)
    """
    try:
        # Check if index already exists
        redis_client_raw.ft(INDEX_NAME).info()
        return  # Index exists, nothing to do

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
                "DIM": VECTOR_DIM,       # 768 dimensions
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
    4. Generate embedding vectors for all chunks (batched)
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
        repo_chunks = text_splitter.split_text(readme)

        for chunk in repo_chunks:
            chunks.append(chunk)
            metadata.append({
                "username": username,
                "repo_name": repo["name"],
            })

    if not chunks:
        return 0

    # Step 4: Generate embeddings for all chunks at once (batched = faster)
    embeddings_model = _get_embeddings_model()
    vectors = embeddings_model.embed_documents(chunks)

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
    # RediSearch tags require escaping of special characters like hyphens
    escaped_username = username
    for char in r",./-+*?^$()[]{}|\:!@#%&=<>":
        escaped_username = escaped_username.replace(char, f"\\{char}")

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
