"""
FastAPI dependency injection for database pool, orchestrator, and repositories.
"""

import src.core.lifespan
from fastapi import Header, HTTPException
from src.database.repositories.project_repository import ProjectRepository
from src.database.repositories.thread_repository import ThreadRepository
from src.database.repositories.queue_repository import QueueRepository
from src.services.redis_client import get_redis_client
from src.core.config import settings

def get_pool():
    """Return the global database connection pool."""
    if src.core.lifespan.pool is None:
        raise RuntimeError("Database pool not initialized")
    return src.core.lifespan.pool

def get_orchestrator():
    """Return the global orchestrator instance."""
    if src.core.lifespan.orchestrator is None:
        raise RuntimeError("Orchestrator not initialized")
    return src.core.lifespan.orchestrator

def get_project_repo():
    """Return a new ProjectRepository instance (uses the global pool)."""
    return ProjectRepository(get_pool())

def get_thread_repo():
    """Return a new ThreadRepository instance (uses the global pool)."""
    return ThreadRepository(get_pool())

def get_queue_repo():
    """Return a new QueueRepository instance (uses the global pool)."""
    return QueueRepository(get_pool())

async def get_redis():
    """Return the Redis client instance."""
    return await get_redis_client()

async def verify_admin_token(authorization: str = Header(...)) -> None:
    """
    Проверяет Bearer-токен в заголовке Authorization.
    Используется для защиты эндпоинтов, доступных только администратору.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid token format")
    token = authorization[7:]
    if token != settings.ADMIN_API_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid admin token")
