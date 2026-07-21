"""
Indexing Pipeline Configuration
================================
Centralized, tunable constants for the GitHub RAG indexing pipeline.

All indexing behaviour is controlled from this single file.
Import `from app.core.indexing_config import *` in services that
need these values.

Tuning Guide
------------
- MAX_REPOS_TO_INDEX: Lower = faster, higher = more coverage.
- MIN_README_LENGTH: Raise to skip boilerplate READMEs (e.g. 500).
- CHUNK_SIZE: 1500 is optimal for README prose (≈375 words).
- EMBEDDING_BATCH_SIZE: Match to your embedding API's max batch size.
- EMBEDDING_MAX_WORKERS: Keep ≤ 5 to avoid rate-limiting on free tiers.
"""

# ── Repository Filtering ────────────────────────────────────────────
MAX_REPOS_TO_INDEX: int = 10       # Index only the top N repos by popularity
MIN_README_LENGTH: int = 300       # Skip READMEs shorter than this (chars)
SKIP_FORKS: bool = True            # Skip forked repositories
SKIP_ARCHIVED: bool = True         # Skip archived repositories

# ── Text Chunking ───────────────────────────────────────────────────
CHUNK_SIZE: int = 1500             # Characters per chunk (~375 words)
CHUNK_OVERLAP: int = 150           # Overlap between consecutive chunks

# ── Embedding Generation ────────────────────────────────────────────
EMBEDDING_BATCH_SIZE: int = 32     # Texts per embedding API call
EMBEDDING_MAX_WORKERS: int = 5     # Parallel threads for embedding batches
EMBEDDING_API_TIMEOUT: float = 60.0  # Timeout per API call (seconds)
EMBEDDING_MAX_RETRIES: int = 3     # Retry attempts for transient failures

# ── Redis Storage ───────────────────────────────────────────────────
REDIS_PIPELINE_BATCH: int = 100    # Hashes per Redis pipeline flush
CACHE_TTL_SECONDS: int = 86400     # 24h TTL for completed analysis cache
REPO_CACHE_TTL_SECONDS: int = 86400  # 24h TTL for per-repo SHA cache
