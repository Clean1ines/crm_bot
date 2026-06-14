"""
API endpoints for viewing current rate limit status of Groq models.
"""

from fastapi import APIRouter, Depends

from src.contexts.llm_runtime.infrastructure.providers.groq.groq_model_catalog_seed import (
    build_groq_free_plan_model_profiles,
)
from src.infrastructure.llm.rate_limit_tracker import RateLimitTracker
from src.interfaces.http.dependencies import require_platform_admin

router = APIRouter()


@router.get("/limits", dependencies=[Depends(require_platform_admin)])
async def get_rate_limits():
    tracker = RateLimitTracker()
    model_ids = [
        profile.model_id.value for profile in build_groq_free_plan_model_profiles()
    ]
    limits = await tracker.get_all_remaining(model_ids)
    return {"models": limits}
