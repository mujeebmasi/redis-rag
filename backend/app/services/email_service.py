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
import httpx
from email.message import EmailMessage
from app.core.config import settings


def send_otp_email(receiver_email: str, otp: str) -> None:
    """Send an OTP code to the specified email address. Falls back to SMTP or console log."""
    # Always print OTP to stdout for easy developer debugging and access via logs
    print(f"--- [DEVELOPER DEBUG] OTP generated for {receiver_email}: {otp} ---", flush=True)

    # 1. Attempt sending via Resend HTTP API (recommended for production/Render to bypass firewall SMTP blocks)
    if settings.RESEND_API_KEY:
        try:
            print(f"Attempting to send OTP via Resend API to {receiver_email}...", flush=True)
            response = httpx.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {settings.RESEND_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": "RedisRAG <onboarding@resend.dev>",
                    "to": receiver_email,
                    "subject": "Your RedisRAG OTP Code",
                    "html": f"""
                    <div style="font-family: 'Outfit', sans-serif; padding: 20px; border: 1px solid #f3e8e2; border-radius: 12px; max-width: 500px; margin: 0 auto; background-color: #fdfbfc;">
                        <h2 style="color: #ff5a36; font-size: 20px; margin-bottom: 10px;">RedisRAG Verification</h2>
                        <p style="font-size: 15px; color: #1e293b; line-height: 1.5;">Hello,</p>
                        <p style="font-size: 15px; color: #1e293b; line-height: 1.5;">Your one-time passcode (OTP) for RedisRAG is:</p>
                        <div style="font-size: 32px; font-weight: bold; letter-spacing: 5px; padding: 15px; margin: 15px 0; background-color: rgba(255, 90, 54, 0.05); color: #ff5a36; border-radius: 8px; text-align: center;">{otp}</div>
                        <p style="font-size: 13px; color: #64748b;">This OTP is valid for 5 minutes.</p>
                        <hr style="border: 0; border-top: 1px solid #f3e8e2; margin: 20px 0;" />
                        <p style="font-size: 11px; color: #94a3b8;">If you did not request this login code, you can safely ignore this email.</p>
                    </div>
                    """,
                },
                timeout=5.0,
            )
            response.raise_for_status()
            print(f"OTP successfully sent via Resend API to {receiver_email}.", flush=True)
            return
        except Exception as e:
            print(f"WARNING: Resend API failed: {e}. Falling back to SMTP/logs.", flush=True)

    # 2. Fallback to Gmail SMTP (for local dev or if ports are unblocked)
    if settings.EMAIL_ADDRESS and settings.EMAIL_PASSWORD:
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
                return
        except Exception as e:
            print(
                f"WARNING: Failed to send email via SMTP to {receiver_email}: {e}. "
                "Outbound SMTP port 465 is likely blocked by your cloud provider. "
                "Please check the log above for the OTP code to log in.",
                flush=True
            )
    else:
        print("SMTP/Resend credentials not configured or failed. Please use the log output above for login.", flush=True)