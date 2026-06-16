from fastapi import APIRouter
from app.services.email_service import send_otp_email
from app.schemas.auth import (
    SendOTPRequest,
    VerifyOTPRequest
)
from app.services.otp_service import generate_otp
from app.core.redis_client import redis_client

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"]
)


@router.post("/send-otp")
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
def verify_otp(data: VerifyOTPRequest):

    stored_otp = redis_client.get(
        f"otp:{data.email}"
    )
  

    print("User OTP:", data.otp)
    print("Stored OTP:", stored_otp)

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

    redis_client.delete(
        f"otp:{data.email}"
    )

    return {
        "verified": True,
        "message": "OTP verified successfully"
    }