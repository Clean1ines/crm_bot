"""
Redis-based distributed locking utilities for thread-level concurrency control.
Provides functions to acquire and release locks per thread ID to prevent race conditions
when processing multiple messages for the same conversation thread.
"""

from src.infrastructure.logging.logger import get_logger
from src.infrastructure.redis.client import get_redis_client

logger = get_logger(__name__)

# Prefix for Redis lock keys
LOCK_KEY_PREFIX = "lock:thread:"


async def acquire_thread_lock(thread_id: str, ttl: int = 30) -> bool:
    """
    Attempt to acquire a lock for a specific thread.

    Uses Redis SET with NX (only set if not exists) and EX (expiry) to create a lock.
    If the lock already exists, returns False immediately.

    Args:
        thread_id: The UUID of the thread to lock.
        ttl: Time-to-live in seconds for the lock (default 30). After this period,
             the lock will be automatically released even if not explicitly unlocked.

    Returns:
        True if the lock was successfully acquired, False otherwise.

    Raises:
        RuntimeError: If Redis client is not configured or connection fails.
    """
    redis = await get_redis_client()
    key = f"{LOCK_KEY_PREFIX}{thread_id}"
    # nx=True -> only set if key does not exist, ex=ttl -> set expiry in seconds
    acquired = await redis.set(key, "1", nx=True, ex=ttl)
    if acquired:
        logger.debug("Acquired lock", extra={"thread_id": thread_id, "ttl": ttl})
    else:
        logger.debug("Lock already held", extra={"thread_id": thread_id})
    return bool(acquired)


async def release_thread_lock(thread_id: str) -> None:
    """
    Explicitly release a lock for a specific thread.

    Deletes the lock key from Redis. Does nothing if the lock does not exist.

    Args:
        thread_id: The UUID of the thread to unlock.

    Raises:
        RuntimeError: If Redis client is not configured or connection fails.
    """
    redis = await get_redis_client()
    key = f"{LOCK_KEY_PREFIX}{thread_id}"
    deleted = await redis.delete(key)
    if deleted:
        logger.debug("Released lock", extra={"thread_id": thread_id})
    else:
        logger.debug(
            "Lock already released or never held", extra={"thread_id": thread_id}
        )
