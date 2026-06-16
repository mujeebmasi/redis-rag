
from pydantic import BaseModel


class VerifyOTPRequest(BaseModel):
    email: str
    otp: str