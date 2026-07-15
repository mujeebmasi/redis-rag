"""
Chat API Routes
===============
AI-powered chat about GitHub profiles using RAG.

Endpoints:
    POST /chat → Ask a question about a GitHub user's projects

Prerequisite: The user's profile must be analyzed first (POST /github/analyze)
so that README embeddings exist in the vector database.
"""

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.auth import get_current_user
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.rag_service import ask

router = APIRouter(
    prefix="/chat",
    tags=["AI Chat"],
)


@router.post("", response_model=ChatResponse)
def chat_with_ai(
    data: ChatRequest,
    user: dict = Depends(get_current_user),
):
    """
    Ask an AI question about a GitHub user's projects.
    
    The AI uses Retrieval-Augmented Generation (RAG):
    1. Searches Redis Vector DB for relevant README chunks
    2. Sends them as context to Google Gemini LLM
    3. Returns a grounded, accurate answer
    
    Requires:
    - JWT Authentication (Bearer token)
    - Profile must be analyzed first (POST /github/analyze)
    
    Example:
        {
            "username": "torvalds",
            "question": "What projects does this user maintain?"
        }
    """

    try:
        result = ask(
            username=data.username,
            question=data.question,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AI service error: {str(e)}",
        )

    return ChatResponse(
        answer=result["answer"],
        sources=result["sources"],
    )

