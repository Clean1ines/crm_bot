"""
Redis client singleton for temporary storage (e.g., awaiting manager replies).
"""

import redis.asyncio as redis
from src.core.config import settings
from src.core.logging import get_logger

logger = get_logger(__name__)

_redis_client = None

async def get_redis_client() -> redis.Redis:
    """
    Return a singleton async Redis client connected to the URL from settings.
    """
    global _redis_client
    if _redis_client is None:
        if not settings.REDIS_URL:
            logger.error("REDIS_URL is not set in environment")
            raise RuntimeError("REDIS_URL is not set in environment")
        logger.info("Creating Redis client")
        _redis_client = await redis.from_url(
            settings.REDIS_URL,
            decode_responses=True  # so we get strings, not bytes
        )
    return _redis_client
