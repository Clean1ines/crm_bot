"""
Logging endpoint for frontend log drain.
"""

from fastapi import APIRouter, Request
from src.infrastructure.logging.logger import get_logger

router = APIRouter(prefix="/api/logs", tags=["logs"])
logger = get_logger(__name__)


@router.post("/frontend")
async def frontend_logs(request: Request):
    """
    Receive structured logs from frontend and forward to backend logger.
    This endpoint is used by the frontend in production to send logs to Render Log Drain.
    """
    data = await request.json()
    level = data.get("level", "info")
    message = data.get("message", "")
    # Extract extra fields (everything except level, message, timestamp)
    extra = {k: v for k, v in data.items() if k not in ("level", "message", "timestamp")}
    # Map frontend log levels to backend log methods
    if level == "debug":
        logger.debug(message, extra=extra)
    elif level == "info":
        logger.info(message, extra=extra)
    elif level == "warn":
        logger.warning(message, extra=extra)
    elif level == "error":
        logger.error(message, extra=extra)
    else:
        # Fallback to info
        logger.info(message, extra=extra)
    return {"status": "ok"}
