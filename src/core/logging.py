"""
Structured logging configuration using structlog.
Provides a middleware for FastAPI to inject correlation IDs.
"""

import structlog
import logging
import uuid
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import sys

def configure_logging():
    """Configure structlog for JSON output with timestamps and levels."""
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Configure root logger to use structlog
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(structlog.stdlib.ProcessorFormatter(
        processor=structlog.processors.JSONRenderer()
    ))
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """
    Middleware that adds a correlation ID to each request and injects it into the log context.
    """
    async def dispatch(self, request: Request, call_next):
        correlation_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        # Bind correlation ID to structlog context for this request
        with structlog.contextvars.bound_contextvars(correlation_id=correlation_id):
            response = await call_next(request)
            response.headers["X-Request-ID"] = correlation_id
            return response


# Helper to get a logger bound with static context (e.g., module name)
def get_logger(module_name: str) -> structlog.stdlib.BoundLogger:
    """Return a structlog logger bound with the module name."""
    return structlog.get_logger(module_name)
