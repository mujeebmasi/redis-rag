"""
RedisRAG - AI Powered GitHub Profile Analyzer
==============================================
Main FastAPI application entry point.

Run with:
    uvicorn app.main:app --reload

Swagger Docs:
    http://127.0.0.1:8000/docs
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.exceptions import RedisError, ResponseError

from app.api.chat import router as chat_router
from app.api.github import router as github_router
from app.core.config import settings
from app.core.redis_client import redis_client

# Send logger.info(...) output to stdout, so it shows up in Render's logs
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

# ── FastAPI App ──────────────────────────────────────────────────────

app = FastAPI(
    title="RedisRAG",
    description=(
        "AI-powered GitHub Profile Analyzer using "
        "Retrieval-Augmented Generation (RAG). "
        "Analyze any GitHub profile and chat with AI about their projects."
    ),
    version="1.1.1",
)

# ── CORS Middleware ──────────────────────────────────────────────────
# Allows the frontend (on a different domain) to call this API.
# allow_credentials must stay False with "*": the app uses no cookies.

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Register Routers ────────────────────────────────────────────────

app.include_router(github_router)    # /github/*
app.include_router(chat_router)      # /chat


# ── Health Endpoints ─────────────────────────────────────────────────

@app.get("/", tags=["Health"])
def root():
    """Liveness check — the frontend calls this to wake the server up."""
    return {
        "app": "RedisRAG",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health", tags=["Health"])
def health():
    """
    Deployment check: is Redis reachable, does it support vector search,
    and are the API keys set? (Only says whether keys exist, never their values.)
    """
    redis_status = "ok"
    try:
        redis_client.ping()
        try:
            redis_client.execute_command("FT._LIST")
        except ResponseError:
            redis_status = "no vector search (needs Redis Stack / Redis 8)"
    except RedisError:
        redis_status = "unreachable"

    return {
        "status": "ok" if redis_status == "ok" else "degraded",
        "redis": redis_status,
        "gemini_key_set": bool(settings.GOOGLE_API_KEY),
        "groq_key_set": bool(settings.GROQ_API_KEY),
        "github_token_set": bool(settings.GITHUB_TOKEN),
    }
