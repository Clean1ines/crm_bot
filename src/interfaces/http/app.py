"""
Canonical FastAPI application assembly for the HTTP interface layer.
"""

import traceback

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.application.errors import ApplicationError
from src.infrastructure.app.lifespan import lifespan
from src.infrastructure.config.settings import settings
from src.infrastructure.logging.logger import CorrelationIdMiddleware, configure_logging, get_logger
from src.interfaces.http.auth import router as auth_router
from src.interfaces.http.bot import router as bot_router
from src.interfaces.http.chat import router as chat_router
from src.interfaces.http.clients import router as clients_router
from src.interfaces.http.knowledge import router as knowledge_router
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


@app.exception_handler(ApplicationError)
async def application_error_handler(request, exc: ApplicationError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers={"Access-Control-Allow-Origin": settings.FRONTEND_URL if settings.FRONTEND_URL else "*"},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"GLOBAL ERROR: {str(exc)}\n{traceback.format_exc()}")
    return JSONResponse(
        status_code=500,
        content={
            "error": str(exc),
            "traceback": traceback.format_exc(),
            "details": "Check Render logs for full info",
        },
        headers={"Access-Control-Allow-Origin": settings.FRONTEND_URL if settings.FRONTEND_URL else "*"},
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
