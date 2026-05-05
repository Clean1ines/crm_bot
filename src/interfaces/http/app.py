"""
Canonical FastAPI application assembly for the HTTP interface layer.
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.application.errors import ApplicationError
from src.interfaces.composition.fastapi_lifespan import lifespan
from src.infrastructure.config.settings import settings
from src.infrastructure.logging.logger import (
    CorrelationIdMiddleware,
    configure_logging,
    get_logger,
)
from src.interfaces.http.auth import router as auth_router
from src.interfaces.http.bot import router as bot_router
from src.interfaces.http.chat import router as chat_router
from src.interfaces.http.clients import router as clients_router
from src.interfaces.http.knowledge import (
    UPLOAD_TOO_LARGE_DETAIL,
    router as knowledge_router,
)
from src.interfaces.http.limits import router as limits_router
from src.interfaces.http.logs import router as logs_router
from src.interfaces.http.metrics import router as metrics_router
from src.interfaces.http.projects import router as projects_router
from src.interfaces.http.threads import router as threads_router
from src.interfaces.http.webhooks import router as webhooks_router

configure_logging()
logger = get_logger(__name__)

app = FastAPI(title=settings.PROJECT_NAME, lifespan=lifespan)

origins = ["https://crm-bot-panel.onrender.com"]
if settings.FRONTEND_URL and settings.FRONTEND_URL not in origins:
    origins.append(settings.FRONTEND_URL)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(CorrelationIdMiddleware)

KNOWLEDGE_UPLOAD_MULTIPART_OVERHEAD_BYTES = 64 * 1024


def _is_knowledge_upload_request(request: Request) -> bool:
    """
    Match only the document upload endpoint, not list/preview/usage/delete routes.

    The upload route is:
    POST /api/projects/{project_id}/knowledge
    """
    if request.method != "POST":
        return False

    path = request.url.path.strip("/")
    parts = path.split("/")
    return (
        len(parts) == 4
        and parts[0] == "api"
        and parts[1] == "projects"
        and parts[3] == "knowledge"
    )


@app.middleware("http")
async def reject_oversized_knowledge_uploads(
    request: Request,
    call_next,
):
    """
    Reject clearly oversized knowledge uploads before FastAPI parses multipart form data.

    Endpoint-level UploadFile validation happens after Starlette/python-multipart has
    parsed the request body. This guard uses Content-Length to avoid spending CPU/RAM
    on requests that cannot possibly fit the configured upload limit.
    """
    if _is_knowledge_upload_request(request):
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                declared_size = int(content_length)
            except ValueError:
                declared_size = 0

            max_request_size = (
                settings.KNOWLEDGE_UPLOAD_MAX_BYTES
                + KNOWLEDGE_UPLOAD_MULTIPART_OVERHEAD_BYTES
            )
            if declared_size > max_request_size:
                request_id = _request_id_from_request(request)
                headers = _cors_headers()
                headers["X-Request-ID"] = request_id
                return JSONResponse(
                    status_code=413,
                    content={
                        "detail": UPLOAD_TOO_LARGE_DETAIL,
                        "request_id": request_id,
                    },
                    headers=headers,
                )

    return await call_next(request)


def _cors_headers() -> dict[str, str]:
    return {
        "Access-Control-Allow-Origin": settings.FRONTEND_URL
        if settings.FRONTEND_URL
        else "*"
    }


def _request_id_from_request(request: Request) -> str:
    """
    Return the correlation/request ID bound by CorrelationIdMiddleware.

    The fallback to the incoming header keeps the error response useful even if
    middleware state is unavailable for some reason.
    """
    return str(
        getattr(request.state, "correlation_id", None)
        or request.headers.get("X-Request-ID")
        or "unknown"
    )


@app.exception_handler(ApplicationError)
async def application_error_handler(request: Request, exc: ApplicationError):
    request_id = _request_id_from_request(request)
    headers = _cors_headers()
    headers["X-Request-ID"] = request_id

    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "request_id": request_id},
        headers=headers,
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Handle unexpected errors without leaking internals to clients.

    Exception details stay in structured logs via exc_info=True.
    The HTTP response intentionally contains no exception string or stack details.
    """
    request_id = _request_id_from_request(request)

    logger.error(
        f"Unhandled HTTP exception: {exc}",
        request_id=request_id,
        method=request.method,
        path=str(request.url.path),
        exc_info=True,
    )

    headers = _cors_headers()
    headers["X-Request-ID"] = request_id

    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "request_id": request_id,
        },
        headers=headers,
    )


app.include_router(webhooks_router)
app.include_router(knowledge_router)
app.include_router(auth_router)
app.include_router(bot_router)
app.include_router(projects_router)
app.include_router(threads_router)
app.include_router(chat_router)
app.include_router(metrics_router)
app.include_router(clients_router)
app.include_router(logs_router)
app.include_router(limits_router)
