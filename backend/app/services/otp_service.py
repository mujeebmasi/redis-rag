"""
OTP Service
===========
Generates a random 6-digit One-Time Password.

The OTP is stored in Redis with a 5-minute expiration (handled in the auth route).
"""

import random


def generate_otp() -> str:
    """Generate a random 6-digit OTP string."""
    return str(random.randint(100000, 999999))