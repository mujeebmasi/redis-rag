from fastapi import APIRouter
from app.services.otp_service import generate_otp
from app.core.redis_client import redis_client

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"]
)


@router.post("/send-otp")
def send_otp(email: str):
    otp = generate_otp()

    redis_client.set(
        f"otp:{email}",
        otp,
        ex=300
    )

    return {
        "message": "OTP generated successfully",
        "otp": otp
    }
    
    
@router.post("/verify-otp")
def verify_otp(email: str, otp: str):

    stored_otp = redis_client.get(f"otp:{email}")
    if not stored_otp:
        return {
            "verified": False,
            "message": "OTP expired"
        }
    if stored_otp != otp:
        return {
            "verified": False,
            "message": "Invalid OTP"
        }

    redis_client.delete(f"otp:{email}")

    return {
        "verified": True,
        "message": "OTP verified successfully"
    }