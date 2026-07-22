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
    """Send an OTP code to the specified email address. Supports Brevo API, Resend API, and SMTP with STARTTLS."""
    # Always print OTP to stdout for easy developer debugging and access via logs
    print(f"--- [DEVELOPER DEBUG] OTP generated for {receiver_email}: {otp} ---", flush=True)

    html_content = f"""
    <div style="font-family: 'Outfit', sans-serif; padding: 20px; border: 1px solid #f3e8e2; border-radius: 12px; max-width: 500px; margin: 0 auto; background-color: #fdfbfc;">
        <h2 style="color: #ff5a36; font-size: 20px; margin-bottom: 10px;">RedisRAG Verification</h2>
        <p style="font-size: 15px; color: #1e293b; line-height: 1.5;">Hello,</p>
        <p style="font-size: 15px; color: #1e293b; line-height: 1.5;">Your one-time passcode (OTP) for RedisRAG is:</p>
        <div style="font-size: 32px; font-weight: bold; letter-spacing: 5px; padding: 15px; margin: 15px 0; background-color: rgba(255, 90, 54, 0.05); color: #ff5a36; border-radius: 8px; text-align: center;">{otp}</div>
        <p style="font-size: 13px; color: #64748b;">This OTP is valid for 5 minutes.</p>
        <hr style="border: 0; border-top: 1px solid #f3e8e2; margin: 20px 0;" />
        <p style="font-size: 11px; color: #94a3b8;">If you did not request this login code, you can safely ignore this email.</p>
    </div>
    """

    # 1. Attempt sending via Brevo HTTP API (Free 300 emails/day to ANY email recipient, no domain required)
    if settings.BREVO_API_KEY:
        try:
            print(f"Attempting to send OTP via Brevo API to {receiver_email}...", flush=True)
            sender_email = settings.EMAIL_ADDRESS or "noreply@redisrag.com"
            response = httpx.post(
                "https://api.brevo.com/v3/smtp/email",
                headers={
                    "api-key": settings.BREVO_API_KEY,
                    "Content-Type": "application/json",
                },
                json={
                    "sender": {"name": "RedisRAG", "email": sender_email},
                    "to": [{"email": receiver_email}],
                    "subject": "Your RedisRAG OTP Code",
                    "htmlContent": html_content,
                },
                timeout=5.0,
            )
            if response.is_error:
                print(f"WARNING: Brevo API failed ({response.status_code}): {response.text}.", flush=True)
            else:
                print(f"OTP successfully sent via Brevo API to {receiver_email}.", flush=True)
                return
        except Exception as e:
            print(f"WARNING: Brevo API request exception: {e}.", flush=True)

    # 2. Attempt sending via Resend HTTP API
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
                    "from": settings.RESEND_FROM_EMAIL,
                    "to": receiver_email,
                    "subject": "Your RedisRAG OTP Code",
                    "html": html_content,
                },
                timeout=5.0,
            )
            if response.is_error:
                print(
                    f"WARNING: Resend API failed ({response.status_code}): {response.text}. "
                    "Note: 'onboarding@resend.dev' can only send to your own registered email until you verify a custom domain.",
                    flush=True,
                )
            else:
                print(f"OTP successfully sent via Resend API to {receiver_email}.", flush=True)
                return
        except Exception as e:
            print(f"WARNING: Resend API request exception: {e}.", flush=True)

    # 3. Fallback to SMTP (supports port 587 STARTTLS & port 465 SSL)
    if settings.EMAIL_ADDRESS and settings.EMAIL_PASSWORD:
        email = EmailMessage()
        email["Subject"] = "Your RedisRAG OTP Code"
        email["From"] = settings.EMAIL_ADDRESS
        email["To"] = receiver_email
        email.set_content(f"Your RedisRAG OTP is: {otp}\n\nThis OTP will expire in 5 minutes.")

        try:
            if settings.SMTP_PORT == 465:
                with smtplib.SMTP_SSL(settings.SMTP_HOST, 465, timeout=5.0) as smtp:
                    smtp.login(settings.EMAIL_ADDRESS, settings.EMAIL_PASSWORD)
                    smtp.send_message(email)
            else:
                with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=5.0) as smtp:
                    smtp.starttls()
                    smtp.login(settings.EMAIL_ADDRESS, settings.EMAIL_PASSWORD)
                    smtp.send_message(email)
            print(f"OTP successfully sent via SMTP to {receiver_email}.", flush=True)
            return
        except Exception as e:
            print(
                f"WARNING: Failed to send email via SMTP to {receiver_email}: {e}. "
                "Port is likely blocked by your cloud provider. Please check logs for the OTP code.",
                flush=True,
            )
    else:
        print("SMTP/Resend/Brevo credentials not configured or failed. Use the log output above for OTP.", flush=True)