"""
Chat API Routes
===============
AI-powered chat about GitHub profiles using RAG.

Endpoints:
    POST /chat → Ask a question about a GitHub user's projects

Prerequisite: The user's profile must be analyzed first (POST /github/analyze)
so that README embeddings exist in the vector database.
"""

import logging

from fastapi import APIRouter, HTTPException, status
from redis.exceptions import RedisError

from app.api.github import REDIS_DOWN_MESSAGE, normalize_username
from app.core.errors import UserFacingError
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.rag_service import ask

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/chat",
    tags=["AI Chat"],
)

MAX_QUESTION_LENGTH = 1000


@router.post("", response_model=ChatResponse)
def chat_with_ai(data: ChatRequest):
    """
    Ask an AI question about a GitHub user's projects.

    The AI uses Retrieval-Augmented Generation (RAG):
    1. Searches Redis Vector DB for relevant README chunks
    2. Sends them, plus a profile overview, as context to the Groq LLM
    3. Returns a grounded answer and the source repositories

    Example:
        {
            "username": "torvalds",
            "question": "What projects does this user maintain?"
        }
    """
    username = normalize_username(data.username)
    question = data.question.strip()
    if not question:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Please type a question.")
    if len(question) > MAX_QUESTION_LENGTH:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"Please keep questions under {MAX_QUESTION_LENGTH} characters.",
        )

    try:
        result = ask(username=username, question=question)
    except UserFacingError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(e))
    except RedisError as e:
        logger.error(f"Redis unavailable in /chat: {e}")
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=REDIS_DOWN_MESSAGE)
    except Exception as e:
        # Full details in the server log; the browser only gets a generic message
        logger.exception(f"Unexpected error in /chat: {e}")
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Something went wrong on the server. Please try again.",
        )

    return ChatResponse(
        answer=result["answer"],
        sources=result["sources"],
    )
