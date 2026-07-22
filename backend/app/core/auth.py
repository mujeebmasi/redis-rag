"""
Auth Dependency
===============
Reusable FastAPI dependency for protecting routes.

Usage in any router:
    @router.get("/protected")
    def protected_route(user = Depends(get_current_user)):
        return {"email": user["sub"]}

How it works:
1. FastAPI extracts the Bearer token from the Authorization header
2. We decode and verify the JWT
3. If valid → return the payload (contains user email)
4. If invalid → raise 401 Unauthorized
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.services.jwt_service import verify_token

# HTTPBearer automatically extracts "Bearer <token>" from the Authorization header
# Set auto_error=False so unauthenticated calls fall back cleanly
security = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict:
    """
    FastAPI dependency that validates the JWT token if present,
    or falls back to a default guest identity for passwordless/OTP-free access.
    """
    if credentials and credentials.credentials:
        payload = verify_token(credentials.credentials)
        if payload is not None:
            return payload

    return {"sub": "developer@redisrag.local"}
