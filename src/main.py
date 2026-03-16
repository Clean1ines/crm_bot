"""
Main FastAPI application entry point.
Sets up logging, middleware, and includes routers.
"""

from fastapi import FastAPI

from src.core.config import settings
from src.core.logging import configure_logging, CorrelationIdMiddleware, get_logger
from src.core.lifespan import lifespan
from src.api.webhooks import router as webhooks_router
from src.api.knowledge import router as knowledge_router  # NEW

# Configure structured logging
configure_logging()
logger = get_logger(__name__)

# Create FastAPI application with lifespan
app = FastAPI(title=settings.PROJECT_NAME, lifespan=lifespan)

# Add logging middleware
app.add_middleware(CorrelationIdMiddleware)

# Include routers
app.include_router(webhooks_router)
app.include_router(knowledge_router)  # NEW

# For local development, you can run with uvicorn
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
