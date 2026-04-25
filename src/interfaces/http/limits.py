"""
API endpoints for viewing current rate limit status of Groq models.
"""

from fastapi import APIRouter, Depends

from src.infrastructure.logging.logger import get_logger
from src.interfaces.http.dependencies import require_platform_admin
from src.infrastructure.llm.model_registry import ModelRegistry
from src.infrastructure.llm.rate_limit_tracker import RateLimitTracker
from src.infrastructure.redis.client import get_redis_client

logger = get_logger(__name__)
router = APIRouter()


@router.get("/limits", dependencies=[Depends(require_platform_admin)])
async def get_rate_limits():
    """
    Return current remaining rate limits for all configured models.
    """
    registry = ModelRegistry()
    tracker = RateLimitTracker()
    models = registry.get_all_models()
    model_ids = [m["id"] for m in models]
    limits = await tracker.get_all_remaining(model_ids)
    return {"models": limits}
