"""
Redis Client
=============
Creates Redis connections used across the app.

Two clients:
- redis_client: decode_responses=True → for text operations (OTP storage, etc.)
- redis_client_raw: decode_responses=False → for binary vector storage (embeddings)

Why two clients?
- OTP/text operations need decoded strings (decode_responses=True)
- Vector storage needs raw bytes (decode_responses=False)
- Using the text client for vectors would corrupt the binary data
"""

import redis
from app.core.config import settings

# For text operations (OTP, general key-value)
redis_client = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    password=settings.REDIS_PASSWORD,
    decode_responses=True,
    protocol=2
)

# For vector/binary operations (embedding storage & search)
redis_client_raw = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    password=settings.REDIS_PASSWORD,
    decode_responses=False,
    protocol=2
)