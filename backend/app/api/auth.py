from fastapi import APIRouter
from app.services.email_service import send_otp_email
from app.db.dependencies import get_db
from app.services.otp_service import generate_otp
from app.core.redis_client import redis_client
from fastapi import Depends
from sqlalchemy.orm import Session
from typing import Annotated
from fastapi import Header, HTTPException
from app.services.jwt_service import verify_token
from app.services.jwt_service import create_access_token
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.db.crud import (
    get_user_by_email,
    create_user
)
from app.schemas.auth import (
    SendOTPRequest,
    VerifyOTPRequest
)

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"]
)
def get_current_user(
    authorization: Annotated[str, Header()]
):
    token = authorization.replace(
        "Bearer ",
        ""
    )

    payload = verify_token(token)

    if payload is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid token"
        )

    return payload


@router.post("/send-otp")
def send_otp(data: SendOTPRequest):

    otp = generate_otp()

    redis_client.set(
        f"otp:{data.email}",
        otp,
        ex=300
    )

    send_otp_email(
        receiver_email=data.email,
        otp=otp
    )

    return {
        "message": "OTP sent successfully"
    }


@router.post("/verify-otp")
def verify_otp(data: VerifyOTPRequest,
               db: Session = Depends(get_db)):

    stored_otp = redis_client.get(
        f"otp:{data.email}"
    )
  

    if stored_otp is None:
        return {
            "verified": False,
            "message": "No OTP found for this email"
        }

    if stored_otp != data.otp:
        return {
            "verified": False,
            "message": "Invalid OTP"
        }
    existing_user = get_user_by_email(
            db,
            data.email
            )

    if not existing_user:
        create_user(
            db,
            data.email
        )
    redis_client.delete(
        f"otp:{data.email}"
    )
    token = create_access_token(
    data.email
    )
    return {
    "verified": True,
    "message": "OTP verified successfully",
    "access_token": token
}
    
security = HTTPBearer()

# @router.get("/me")
# def get_me(
#     credentials: HTTPAuthorizationCredentials = Depends(security)
# ):
#     return {
#         "token": credentials.credentials
#     }

@router.get("/me")
def get_me(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):

    payload = verify_token(
        credentials.credentials
    )

    return {
        "email": payload["sub"]
    }