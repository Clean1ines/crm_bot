"""
Main FastAPI application entry point.
Sets up logging, middleware, and includes routers.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import traceback

from src.core.config import settings
from src.core.logging import configure_logging, CorrelationIdMiddleware, get_logger
from src.core.lifespan import lifespan
from src.api.webhooks import router as webhooks_router
from src.api.knowledge import router as knowledge_router
from src.api.projects import router as projects_router
from src.api.templates import router as templates_router
from src.api.threads import router as threads_router
from src.api.chat import router as chat_router
from src.api.auth import router as auth_router
from src.api.bot import router as bot_router
from src.api.metrics import router as metrics_router

# Configure structured logging
configure_logging()
logger = get_logger(__name__)

# Create FastAPI application with lifespan
app = FastAPI(title=settings.PROJECT_NAME, lifespan=lifespan)

# CORS configuration (allow frontend domain)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://crm-bot-panel.onrender.com"],  # замените на реальный домен фронтенда
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add logging middleware
app.add_middleware(CorrelationIdMiddleware)

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    # Это выведет ошибку в логи Render и вернет её на фронтенд
    logger.error(f"GLOBAL ERROR: {str(exc)}\n{traceback.format_exc()}")
    return JSONResponse(
        status_code=500,
        content={
            "error": str(exc),
            "traceback": traceback.format_exc(),
            "details": "Check Render logs for full info"
        },
        headers={"Access-Control-Allow-Origin": "https://crm-bot-panel.onrender.com"}
    )

# Include routers
app.include_router(webhooks_router)
app.include_router(knowledge_router)
app.include_router(auth_router)
app.include_router(bot_router)
app.include_router(projects_router)
app.include_router(templates_router)
app.include_router(threads_router)
app.include_router(chat_router)
app.include_router(metrics_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
