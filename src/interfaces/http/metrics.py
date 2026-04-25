"""
API endpoints for metrics and analytics.
"""

from datetime import date
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from src.interfaces.http.dependencies import require_platform_admin, get_metrics_repository
from src.infrastructure.db.repositories.metrics_repository import MetricsRepository
from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/admin/metrics", tags=["admin"])


class AggregateMetricsRequest(BaseModel):
    """Request body for manual metrics aggregation."""
    date: str  # YYYY-MM-DD


@router.post("/aggregate", status_code=status.HTTP_202_ACCEPTED)
async def aggregate_metrics(
    request: AggregateMetricsRequest,
    _: str = Depends(require_platform_admin),
    metrics_repo: MetricsRepository = Depends(get_metrics_repository)
):
    """
    Manually trigger metrics aggregation for a specific date.
    This endpoint is protected by the platform admin role.
    
    In production, this would typically be run as a cron job.
    """
    try:
        target_date = date.fromisoformat(request.date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")
    
    # Enqueue aggregation task
    from src.infrastructure.db.repositories.queue_repository import QueueRepository
    from src.interfaces.http.dependencies import get_pool
    pool = get_pool()
    queue_repo = QueueRepository(pool)
    await queue_repo.enqueue(
        task_type="aggregate_metrics",
        payload={"date": request.date}
    )
    
    logger.info("Aggregation task enqueued", extra={"date": request.date})
    return {"status": "accepted", "message": f"Aggregation for {request.date} enqueued."}
