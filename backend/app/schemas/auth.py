"""
Auth Schemas
============
Pydantic models for request/response validation in auth routes.

Pydantic validates incoming JSON automatically:
- Wrong type? → 422 error with details
- Missing field? → 422 error with details
- Invalid email? → 422 error with details

EmailStr validates that the email format is correct (requires pydantic[email]).
"""

from pydantic import BaseModel, EmailStr


class SendOTPRequest(BaseModel):
    """Request body for POST /auth/send-otp"""
    email: EmailStr


class VerifyOTPRequest(BaseModel):
    """Request body for POST /auth/verify-otp"""
    email: EmailStr
    otp: str