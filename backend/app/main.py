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
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from app.api.auth import router as auth_router
from app.api.github import router as github_router
from app.api.chat import router as chat_router
from app.db.database import Base, engine
from app.db import models  # noqa: F401 — ensures models are registered

# Load environment variables from .env file
load_dotenv()

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create database tables on startup (if they don't exist)."""
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created / verified.")
    except Exception as e:
        logger.warning(
            f"Could not connect to PostgreSQL on startup: {e}. "
            "Auth routes will fail until the database is available."
        )
    yield


# ── FastAPI App ──────────────────────────────────────────────────────

app = FastAPI(
    title="RedisRAG",
    description=(
        "AI-powered GitHub Profile Analyzer using "
        "Retrieval-Augmented Generation (RAG). "
        "Analyze any GitHub profile and chat with AI about their projects."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS Middleware ──────────────────────────────────────────────────
# Allows frontend apps (React, Next.js, etc.) to call this API.
# In production, replace "*" with your frontend's domain.

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Register Routers ────────────────────────────────────────────────

app.include_router(auth_router)      # /auth/*
app.include_router(github_router)    # /github/*
app.include_router(chat_router)      # /chat


# ── Root Endpoint ────────────────────────────────────────────────────

@app.get("/", tags=["Health"])
def root():
    """Health check endpoint."""
    return {
        "app": "RedisRAG",
        "status": "running",
        "docs": "/docs",
    }