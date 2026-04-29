"""
Logging endpoint for frontend log drain.
"""

from collections.abc import Mapping

from fastapi import APIRouter, Request
from src.infrastructure.logging.logger import get_logger

router = APIRouter(prefix="/api/logs", tags=["logs"])
logger = get_logger(__name__)

_KNOWN_LEVELS = {"debug", "info", "warn", "error"}
_RESERVED_KEYS = {"level", "message", "timestamp"}
_MAX_EXTRA_FIELDS = 20
_MAX_CONTAINER_ITEMS = 20
_MAX_KEY_LENGTH = 80
_MAX_VALUE_LENGTH = 500
_MAX_MESSAGE_LENGTH = 2000


def _truncate_text(value: object, *, limit: int) -> str:
    return str(value)[:limit]


def _sanitize_log_value(value: object, *, depth: int = 0) -> object:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return value
    if isinstance(value, str):
        return _truncate_text(value, limit=_MAX_VALUE_LENGTH)
    if depth >= 2:
        return _truncate_text(value, limit=_MAX_VALUE_LENGTH)
    if isinstance(value, list):
        return [
            _sanitize_log_value(item, depth=depth + 1)
            for item in value[:_MAX_CONTAINER_ITEMS]
        ]
    if isinstance(value, Mapping):
        sanitized: dict[str, object] = {}
        for key, item in list(value.items())[:_MAX_CONTAINER_ITEMS]:
            sanitized[_truncate_text(key, limit=_MAX_KEY_LENGTH)] = _sanitize_log_value(
                item,
                depth=depth + 1,
            )
        return sanitized
    return _truncate_text(value, limit=_MAX_VALUE_LENGTH)


def _normalize_level(data: Mapping[str, object]) -> str:
    raw_level = str(data.get("level", "info")).strip().lower()
    return raw_level if raw_level in _KNOWN_LEVELS else "info"


def _normalize_message(data: Mapping[str, object]) -> str:
    return _truncate_text(data.get("message", ""), limit=_MAX_MESSAGE_LENGTH)


def _build_extra(data: Mapping[str, object]) -> dict[str, object]:
    extra: dict[str, object] = {}
    for key, value in list(data.items())[:_MAX_EXTRA_FIELDS]:
        if key in _RESERVED_KEYS:
            continue
        extra[_truncate_text(key, limit=_MAX_KEY_LENGTH)] = _sanitize_log_value(value)
    return extra


@router.post("/frontend")
async def frontend_logs(request: Request):
    """
    Receive structured logs from frontend and forward to backend logger.
    This endpoint is used by the frontend in production to send logs to Render Log Drain.
    """
    data = await request.json()

    if not isinstance(data, dict):
        data = {"message": _truncate_text(data, limit=_MAX_MESSAGE_LENGTH)}

    level = _normalize_level(data)
    message = _normalize_message(data)
    extra = _build_extra(data)

    if level == "debug":
        logger.debug(message, extra=extra)
    elif level == "info":
        logger.info(message, extra=extra)
    elif level == "warn":
        logger.warning(message, extra=extra)
    elif level == "error":
        logger.error(message, extra=extra)
    else:
        logger.info(message, extra=extra)
    return {"status": "ok"}
