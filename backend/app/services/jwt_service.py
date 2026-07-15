"""
JWT Service
===========
Creates and verifies JSON Web Tokens for authentication.

Flow:
1. User verifies OTP → we create a JWT with their email
2. User sends JWT in Authorization header → we verify it
3. If valid → user is authenticated

The token contains:
- "sub" (subject): the user's email
- "exp" (expiration): 1 day from creation
"""

from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError
from app.core.config import settings

ALGORITHM = "HS256"


def create_access_token(email: str) -> str:
    """Create a JWT token with the user's email as the subject."""

    payload = {
        "sub": email,
        "exp": datetime.now(timezone.utc) + timedelta(days=1),
    }

    return jwt.encode(
        payload,
        settings.SECRET_KEY,
        algorithm=ALGORITHM,
    )


def verify_token(token: str) -> dict | None:
    """
    Decode and verify a JWT token.
    
    Returns:
        dict: The token payload if valid
        None: If the token is invalid or expired
    """

    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[ALGORITHM],
        )
        return payload

    except JWTError:
        return None
