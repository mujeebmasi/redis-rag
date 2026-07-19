"""
Email Service
=============
Sends OTP emails via Gmail SMTP.

Setup required:
1. Enable 2-Factor Authentication on your Gmail
2. Generate an App Password (Google Account → Security → App Passwords)
3. Set EMAIL_ADDRESS and EMAIL_PASSWORD in your .env file

Note: EMAIL_PASSWORD is the App Password, NOT your Gmail password.
"""

import smtplib
from email.message import EmailMessage
from app.core.config import settings


def send_otp_email(receiver_email: str, otp: str) -> None:
    """Send an OTP code to the specified email address. Falls back to console log if SMTP is blocked."""
    # Always print OTP to stdout for easy developer debugging and access via logs
    print(f"--- [DEVELOPER DEBUG] OTP generated for {receiver_email}: {otp} ---", flush=True)

    email = EmailMessage()

    email["Subject"] = "Your RedisRAG OTP Code"
    email["From"] = settings.EMAIL_ADDRESS
    email["To"] = receiver_email

    email.set_content(
        f"""
Your OTP is: {otp}

This OTP will expire in 5 minutes.

- RedisRAG
"""
    )

    try:
        # Set a 5-second timeout so the API doesn't hang if SMTP ports are blocked by the host
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=5.0) as smtp:
            smtp.login(
                settings.EMAIL_ADDRESS,
                settings.EMAIL_PASSWORD,
            )
            smtp.send_message(email)
            print(f"OTP successfully sent via SMTP to {receiver_email}.", flush=True)
    except Exception as e:
        print(
            f"WARNING: Failed to send email via SMTP to {receiver_email}: {e}. "
            "Outbound SMTP port 465 is likely blocked by your cloud provider. "
            f"Please check the log above for the OTP code to log in.",
            flush=True
        )