"""
Redis client singleton for temporary storage (e.g., awaiting manager replies).
"""

import redis.asyncio as redis
from src.core.config import settings

_redis_client = None

async def get_redis_client() -> redis.Redis:
    """
    Return a singleton async Redis client connected to the URL from settings.
    """
    global _redis_client
    if _redis_client is None:
        if not settings.REDIS_URL:
            raise RuntimeError("REDIS_URL is not set in environment")
        _redis_client = await redis.from_url(
            settings.REDIS_URL,
            decode_responses=True  # so we get strings, not bytes
        )
    return _redis_client
