"""
Indexing Pipeline Configuration
================================
Centralized, tunable constants for the GitHub RAG indexing pipeline.

All indexing behaviour is controlled from this single file.

Tuning Guide
------------
- MAX_REPOS_TO_INDEX: Lower = faster, higher = more coverage.
- MIN_README_LENGTH: Raise to skip boilerplate READMEs (e.g. 500).
- CHUNK_SIZE: 1500 is optimal for README prose (≈375 words).
- EMBEDDING_DIM: 768 uses 4x less Redis memory than the full 3072.
- INDEXING_MAX_WAIT: How long indexing may pause for Gemini's rate limit.
- DATA_TTL_SECONDS: How long a profile's vectors and cache live in Redis.
"""

# ── Repository Filtering ────────────────────────────────────────────
MAX_REPOS_TO_INDEX: int = 15       # Index only the top N repos by popularity
MIN_README_LENGTH: int = 300       # Skip READMEs shorter than this (chars)
SKIP_FORKS: bool = True            # Skip forked repositories
SKIP_ARCHIVED: bool = True         # Skip archived repositories

# ── Text Chunking ───────────────────────────────────────────────────
CHUNK_SIZE: int = 1500             # Characters per chunk (~375 words)
CHUNK_OVERLAP: int = 150           # Overlap between consecutive chunks

# ── Embedding Generation (Google Gemini) ────────────────────────────
EMBEDDING_MODEL: str = "models/gemini-embedding-001"
EMBEDDING_DIM: int = 768           # Gemini supports 768 / 1536 / 3072
EMBEDDING_BATCH_SIZE: int = 50     # Texts per batchEmbedContents call
EMBEDDING_API_TIMEOUT: float = 30.0  # Timeout per API call (seconds)
EMBEDDING_MAX_RETRIES: int = 3     # Retry attempts for 429 / 5xx / timeouts
# Gemini's free tier limits requests per minute. After a 429 we wait as long
# as Gemini asks (usually under a minute), or a full minute if it doesn't say.
EMBEDDING_RATE_LIMIT_WAIT: float = 60.0  # Pause after a 429 that gives no hint (s)
INDEXING_MAX_WAIT: float = 90.0    # Indexing: longer pauses (e.g. daily quota) fail instead
CHAT_MAX_WAIT: float = 5.0         # Chat: nobody waits a minute for an answer

# ── Retrieval ───────────────────────────────────────────────────────
TOP_K: int = 5                     # README chunks sent to the LLM per question

# ── Redis Storage ───────────────────────────────────────────────────
REDIS_PIPELINE_BATCH: int = 100    # Hashes per Redis pipeline flush
DATA_TTL_SECONDS: int = 86400      # 24h: vectors, SHA cache and finished status
STATUS_TTL_SECONDS: int = 3600     # 1h: "processing" and "failed" status
LOCK_TTL_SECONDS: int = 300        # 5 min: one indexing job per user at a time
