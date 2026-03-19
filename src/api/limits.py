"""
API endpoints for viewing current rate limit status of Groq models.
"""

from fastapi import APIRouter, Depends, HTTPException

from src.core.logging import get_logger
from src.api.dependencies import verify_admin_token
from src.core.model_registry import ModelRegistry
from src.services.rate_limit_tracker import RateLimitTracker
from src.services.redis_client import get_redis_client

logger = get_logger(__name__)
router = APIRouter()


@router.get("/limits", dependencies=[Depends(verify_admin_token)])
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
