"""
Auth API Routes
===============
Handles the email OTP authentication flow.

Endpoints:
    POST /auth/send-otp   → Send an OTP to user's email
    POST /auth/verify-otp → Verify OTP and get JWT token
    GET  /auth/me         → Get current user info (protected)

Authentication Flow:
    1. User submits email → OTP generated and stored in Redis (5 min TTL)
    2. OTP sent via Gmail SMTP
    3. User submits email + OTP → verified against Redis
    4. If valid → user created in PostgreSQL (if new) → JWT returned
    5. JWT used for all subsequent protected requests
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.auth import get_current_user
from app.core.redis_client import redis_client
from app.db.crud import get_user_by_email, create_user
from app.db.dependencies import get_db
from app.schemas.auth import SendOTPRequest, VerifyOTPRequest
from app.services.email_service import send_otp_email
from app.services.jwt_service import create_access_token
from app.services.otp_service import generate_otp

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


# ── Send OTP ────────────────────────────────────────────────────────


@router.post("/send-otp")
def send_otp(data: SendOTPRequest):
    """
    Generate a 6-digit OTP, store it in Redis (5 min TTL),
    and send it to the user's email.
    """

    otp = generate_otp()

    # Store in Redis with 5-minute expiration
    redis_client.set(
        f"otp:{data.email}",
        otp,
        ex=300,
    )

    # Send via email
    send_otp_email(
        receiver_email=data.email,
        otp=otp,
    )

    return {
        "message": "OTP sent successfully",
    }


# ── Verify OTP ──────────────────────────────────────────────────────


@router.post("/verify-otp")
def verify_otp(
    data: VerifyOTPRequest,
    db: Session = Depends(get_db),
):
    """
    Verify the OTP against Redis.
    If valid → create user (if new) → return JWT token.
    """

    # Retrieve stored OTP from Redis
    stored_otp = redis_client.get(f"otp:{data.email}")

    # Check for master OTP override (if configured in settings for testing/demo)
    is_master_otp = bool(settings.MASTER_OTP and data.otp == settings.MASTER_OTP)

    if stored_otp is None and not is_master_otp:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OTP expired or not found. Please request a new one.",
        )

    if stored_otp != data.otp and not is_master_otp:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OTP. Please try again.",
        )

    # OTP is valid — clean it up
    redis_client.delete(f"otp:{data.email}")

    # Create user in PostgreSQL if they don't exist yet
    existing_user = get_user_by_email(db, data.email)
    if not existing_user:
        create_user(db, data.email)

    # Generate JWT token
    token = create_access_token(data.email)

    return {
        "verified": True,
        "message": "OTP verified successfully",
        "access_token": token,
    }


# ── Get Current User ────────────────────────────────────────────────


@router.get("/me")
def get_me(user: dict = Depends(get_current_user)):
    """
    Protected route — returns the authenticated user's email.
    Requires: Authorization: Bearer <JWT_TOKEN>
    """

    return {
        "email": user["sub"],
    }