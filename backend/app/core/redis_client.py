"""
Redis Client
=============
Creates Redis connections used across the app.

Two clients:
- redis_client: decode_responses=True → for text operations (job status, cache, logs)
- redis_client_raw: decode_responses=False → for binary vector storage (embeddings)

Why two clients?
- Status/cache operations need decoded strings (decode_responses=True)
- Vector storage needs raw bytes (decode_responses=False)
- Using the text client for vectors would corrupt the binary data

Timeouts:
- Without them, a dead Redis makes every request hang instead of failing.
- With them, the API answers "Redis unreachable" within a few seconds.
"""

import redis

from app.core.config import settings

_COMMON = {
    "host": settings.REDIS_HOST,
    "port": settings.REDIS_PORT,
    "password": settings.REDIS_PASSWORD,
    "protocol": 2,
    "socket_connect_timeout": 5,
    "socket_timeout": 15,
    "health_check_interval": 30,
}

# For text operations (job status, SHA cache, logs)
redis_client = redis.Redis(decode_responses=True, **_COMMON)

# For vector/binary operations (embedding storage & search)
redis_client_raw = redis.Redis(decode_responses=False, **_COMMON)
