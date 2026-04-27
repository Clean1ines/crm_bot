"""
Rate limit tracker for Groq models using Redis.
Updates and retrieves current token/request limits from API response headers.
"""

import json
import time

from src.infrastructure.logging.logger import get_logger
from src.infrastructure.config.settings import settings
from src.infrastructure.redis.client import get_redis_client

logger = get_logger(__name__)


class RateLimitTracker:
    """
    Tracks real‑time rate limits for each model using Redis.
    Data is updated from headers returned by Groq API.
    """
    
    REDIS_PREFIX = settings.RATE_LIMIT_REDIS_PREFIX
    
    def __init__(self):
        self.redis = None  # lazy init
    
    async def _get_redis(self):
        if self.redis is None:
            self.redis = await get_redis_client()
        return self.redis
    
    async def update_from_headers(self, model: str, headers: dict[str, str]) -> None:
        """
        Update rate limit information from Groq response headers.
        Headers include:
          x-ratelimit-limit-requests, x-ratelimit-remaining-requests, x-ratelimit-reset-requests,
          x-ratelimit-limit-tokens, x-ratelimit-remaining-tokens, x-ratelimit-reset-tokens
        """
        redis = await self._get_redis()
        pipe = redis.pipeline()
        
        # Requests (RPD)
        if 'x-ratelimit-limit-requests' in headers:
            limit_req = headers['x-ratelimit-limit-requests']
            remaining_req = headers.get('x-ratelimit-remaining-requests')
            reset_req = headers.get('x-ratelimit-reset-requests')
            if remaining_req is not None:
                key = f"{self.REDIS_PREFIX}{model}:requests_remaining"
                await pipe.set(key, remaining_req)
                if reset_req:
                    # parse reset time (e.g., "2m59.56s") – we store as absolute timestamp? For simplicity keep as string.
                    await pipe.set(f"{key}:reset", reset_req)
                logger.debug("Updated request limit", extra={"model": model, "remaining": remaining_req})
        
        # Tokens (TPM / TPD? headers refer to minute, but we'll store both)
        if 'x-ratelimit-limit-tokens' in headers:
            limit_tok = headers['x-ratelimit-limit-tokens']
            remaining_tok = headers.get('x-ratelimit-remaining-tokens')
            reset_tok = headers.get('x-ratelimit-reset-tokens')
            if remaining_tok is not None:
                key = f"{self.REDIS_PREFIX}{model}:tokens_remaining"
                await pipe.set(key, remaining_tok)
                if reset_tok:
                    await pipe.set(f"{key}:reset", reset_tok)
                logger.debug("Updated token limit", extra={"model": model, "remaining": remaining_tok})
        
        # Also store the last update time for debugging
        await pipe.set(f"{self.REDIS_PREFIX}{model}:last_update", str(time.time()))
        await pipe.execute()
    
    async def get_remaining(self, model: str) -> dict[str, object]:
        """
        Retrieve current remaining limits for a model.
        Returns dict with keys: 'requests_remaining', 'tokens_remaining', 
        'requests_reset', 'tokens_reset', 'last_update'.
        Values are strings or None if not available.
        """
        redis = await self._get_redis()
        keys = [
            f"{self.REDIS_PREFIX}{model}:requests_remaining",
            f"{self.REDIS_PREFIX}{model}:requests_remaining:reset",
            f"{self.REDIS_PREFIX}{model}:tokens_remaining",
            f"{self.REDIS_PREFIX}{model}:tokens_remaining:reset",
            f"{self.REDIS_PREFIX}{model}:last_update"
        ]
        values = await redis.mget(*keys)
        return {
            "requests_remaining": values[0].decode() if values[0] else None,
            "requests_reset": values[1].decode() if values[1] else None,
            "tokens_remaining": values[2].decode() if values[2] else None,
            "tokens_reset": values[3].decode() if values[3] else None,
            "last_update": values[4].decode() if values[4] else None,
        }
    
    async def get_all_remaining(self, models: list[str]) -> dict[str, dict[str, object]]:
        """Get remaining limits for multiple models at once."""
        result = {}
        for model in models:
            result[model] = await self.get_remaining(model)
        return result
    
    async def clear(self, model: str) -> None:
        """Clear all rate limit data for a model (e.g., for testing)."""
        redis = await self._get_redis()
        keys = await redis.keys(f"{self.REDIS_PREFIX}{model}:*")
        if keys:
            await redis.delete(*keys)
            logger.info("Cleared rate limit data", extra={"model": model})
