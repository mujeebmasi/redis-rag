"""
Chat Schemas
============
Pydantic models for the AI chat API.
"""

from pydantic import BaseModel


class ChatRequest(BaseModel):
    """Request body for POST /chat"""
    username: str
    question: str


class ChatResponse(BaseModel):
    """Response from the AI chat endpoint."""
    answer: str
    sources: list[str] = []
