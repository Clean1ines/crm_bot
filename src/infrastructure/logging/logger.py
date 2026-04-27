"""
Structured logging configuration using structlog.
Provides a middleware for FastAPI to inject correlation IDs.
"""

import logging
import sys
import time
import uuid
from collections.abc import Awaitable, Callable, Mapping
from typing import TypeVar

import structlog
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware


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

    # Configure root logger to use structlog.
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processor=structlog.processors.JSONRenderer()
        )
    )
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """
    Middleware that adds a correlation ID to each request and injects it into the log context.
    """

    async def dispatch(self, request: Request, call_next):
        correlation_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.correlation_id = correlation_id

        # Bind correlation ID to structlog context for this request.
        with structlog.contextvars.bound_contextvars(correlation_id=correlation_id):
            response = await call_next(request)
            response.headers["X-Request-ID"] = correlation_id
            return response


def get_logger(module_name: str) -> structlog.stdlib.BoundLogger:
    """Return a structlog logger bound with the module name."""
    return structlog.get_logger(module_name)


StateT = TypeVar("StateT", bound=Mapping[str, object])
ResultT = TypeVar("ResultT")


async def log_node_execution(
    node_name: str,
    func: Callable[[StateT], Awaitable[ResultT]],
    state: StateT,
    get_input_size: Callable[[StateT], int] | None = None,
    get_output_size: Callable[[ResultT], int] | None = None,
) -> ResultT:
    """
    Execute an agent node with timing and observability logging.

    This wrapper measures execution time, computes input/output sizes if provided,
    and logs structured information on success or failure. Exceptions are re-raised.
    """
    trace_id = state.get("trace_id")
    logger = get_logger("node_tracing")
    input_size = get_input_size(state) if get_input_size else 0
    start = time.monotonic()
    error = None
    result = None

    try:
        result = await func(state)
        return result
    except Exception as e:
        error = e
        raise
    finally:
        latency_ms = (time.monotonic() - start) * 1000
        extra: dict[str, object] = {
            "trace_id": trace_id,
            "node": node_name,
            "latency_ms": round(latency_ms, 2),
            "input_size": input_size,
        }
        if error is None:
            if get_output_size and result is not None:
                extra["output_size"] = get_output_size(result)
            logger.info("Node execution completed", **extra)
        else:
            extra["error"] = True
            extra["error_msg"] = str(error)[:200]
            logger.error("Node execution failed", **extra, exc_info=error)
