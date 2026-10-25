"""
Centralized Configuration
=========================
All environment variables are loaded here using pydantic-settings.
Other modules import `settings` from this file instead of calling os.getenv() directly.

Why?
- Single source of truth for all config values
- Automatic validation (missing vars = clear error at startup)
- Type safety (ports are ints, not strings)
- Easy to test (swap settings in tests)
"""

from pathlib import Path

from pydantic_settings import BaseSettings

# Resolve the .env file path relative to the project root (one level above backend/)
_ENV_FILE = Path(__file__).resolve().parent.parent.parent.parent / ".env"


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    Pydantic-settings automatically reads from:
    1. Environment variables
    2. .env file (via model_config)
    """

    # ── Redis (vector store, cache, job status) ─────────────────────
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str | None = None

    # ── GitHub (optional - works without it, but rate limited) ──────
    GITHUB_TOKEN: str | None = None

    # ── AI (Google Gemini embeddings + Groq LLM) ────────────────────
    GOOGLE_API_KEY: str = ""
    GROQ_API_KEY: str = ""
    # llama-3.3-70b-versatile was shut down by Groq on 16 Aug 2026;
    # gpt-oss-120b is Groq's recommended replacement.
    GROQ_MODEL: str = "openai/gpt-oss-120b"

    model_config = {
        "env_file": str(_ENV_FILE),
        "env_file_encoding": "utf-8",
        "extra": "ignore",  # ignore extra vars in .env
    }


# Create a single instance — import this everywhere
settings = Settings()
