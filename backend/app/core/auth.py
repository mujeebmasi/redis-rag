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
# It also adds the 🔒 lock icon in Swagger UI
security = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """
    FastAPI dependency that validates the JWT token and returns the payload.
    
    Raises:
        HTTPException 401: If token is missing, expired, or invalid
    
    Returns:
        dict: JWT payload containing {"sub": "user@email.com", "exp": ...}
    """
    payload = verify_token(credentials.credentials)

    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload
