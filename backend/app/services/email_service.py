import os
import smtplib
from email.message import EmailMessage


def send_otp_email(receiver_email: str, otp: str):

    email = EmailMessage()

    email["Subject"] = "Your OTP Code"
    email["From"] = os.getenv("EMAIL_ADDRESS")
    email["To"] = receiver_email

    email.set_content(
        f"""
Your OTP is: {otp}

This OTP will expire in 5 minutes.
"""
    )

    with smtplib.SMTP_SSL(
        "smtp.gmail.com",
        465
    ) as smtp:

        smtp.login(
            os.getenv("EMAIL_ADDRESS"),
            os.getenv("EMAIL_PASSWORD")
        )

        smtp.send_message(email)