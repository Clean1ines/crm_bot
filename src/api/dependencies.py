"""
FastAPI dependency injection for database pool, orchestrator, and repositories.

This module provides centralized dependency injection functions for:
- Database connection pool
- Orchestrator service
- All repository classes
- Tool registry
- Redis client
- Admin authentication
- JWT authentication (for web users)

All dependencies use the global pool from lifespan management.
"""

from typing import Optional, Any, Callable, Awaitable
from datetime import datetime
import jwt

from fastapi import Header, HTTPException, Depends

from src.core.logging import get_logger
from src.core.config import settings
from src.database.repositories.project_repository import ProjectRepository
from src.database.repositories.thread_repository import ThreadRepository
from src.database.repositories.queue_repository import QueueRepository
from src.database.repositories.event_repository import EventRepository
from src.database.repositories.template_repository import TemplateRepository
from src.database.repositories.workflow_repository import WorkflowRepository
from src.services.redis_client import get_redis_client

import src.core.lifespan

logger = get_logger(__name__)


def get_pool() -> Any:
    """
    Return the global database connection pool.
    
    Raises:
        RuntimeError: If pool is not initialized (called before lifespan startup).
    
    Returns:
        asyncpg.Pool: The global database connection pool.
    """
    if src.core.lifespan.pool is None:
        logger.error("Database pool requested before initialization")
        raise RuntimeError("Database pool not initialized")
    return src.core.lifespan.pool


def get_orchestrator() -> Any:
    """
    Return the global orchestrator instance.
    
    Raises:
        RuntimeError: If orchestrator is not initialized.
    
    Returns:
        OrchestratorService: The global orchestrator instance.
    """
    if src.core.lifespan.orchestrator is None:
        logger.error("Orchestrator requested before initialization")
        raise RuntimeError("Orchestrator not initialized")
    return src.core.lifespan.orchestrator


def get_project_repo(pool: Any = Depends(get_pool)) -> ProjectRepository:
    """
    Return a new ProjectRepository instance.
    
    Args:
        pool: Database connection pool (injected via Depends).
    
    Returns:
        ProjectRepository: Repository for project-level data access.
    """
    return ProjectRepository(pool)


def get_thread_repo(pool: Any = Depends(get_pool)) -> ThreadRepository:
    """
    Return a new ThreadRepository instance.
    
    Args:
        pool: Database connection pool (injected via Depends).
    
    Returns:
        ThreadRepository: Repository for thread/conversation data access.
    """
    return ThreadRepository(pool)


def get_queue_repo(pool: Any = Depends(get_pool)) -> QueueRepository:
    """
    Return a new QueueRepository instance.
    
    Args:
        pool: Database connection pool (injected via Depends).
    
    Returns:
        QueueRepository: Repository for background job queue operations.
    """
    return QueueRepository(pool)


def get_event_repo(pool: Any = Depends(get_pool)) -> EventRepository:
    """
    Return a new EventRepository instance.
    
    Args:
        pool: Database connection pool (injected via Depends).
    
    Returns:
        EventRepository: Repository for event-sourced data access.
    """
    return EventRepository(pool)


def get_template_repo(pool: Any = Depends(get_pool)) -> TemplateRepository:
    """
    Return a new TemplateRepository instance.
    
    Args:
        pool: Database connection pool (injected via Depends).
    
    Returns:
        TemplateRepository: Repository for workflow template operations.
    """
    return TemplateRepository(pool)


def get_workflow_repo(pool: Any = Depends(get_pool)) -> WorkflowRepository:
    """
    Return a new WorkflowRepository instance.
    
    Args:
        pool: Database connection pool (injected via Depends).
    
    Returns:
        WorkflowRepository: Repository for custom workflow operations.
    """
    return WorkflowRepository(pool)


def get_tool_registry() -> Any:
    """
    Return the global ToolRegistry singleton instance.
    
    This dependency provides access to the ToolRegistry for dynamic
    tool execution from canvas workflows and API endpoints.
    
    Returns:
        ToolRegistry: The global tool registry singleton.
    
    Raises:
        RuntimeError: If tool_registry is not initialized.
    """
    # Lazy import to avoid circular dependencies
    from src.tools import tool_registry
    
    if tool_registry is None:
        logger.error("ToolRegistry requested before initialization")
        raise RuntimeError("ToolRegistry not initialized")
    
    return tool_registry


async def get_redis() -> Any:
    """
    Return the Redis client instance.
    
    Returns:
        aioredis.Redis: Async Redis client for temporary state storage.
    """
    return await get_redis_client()


async def get_current_user_id(authorization: Optional[str] = Header(default=None)) -> int:
    """
    Dependency that validates JWT and returns the user's Telegram chat_id.
    """
    if not authorization:
        logger.warning("Authorization header missing")
        raise HTTPException(status_code=401, detail="Authorization header required")
    
    if not authorization.startswith("Bearer "):
        logger.warning("Invalid token format")
        raise HTTPException(status_code=401, detail="Invalid token format. Use 'Bearer <token>'")
    
    token = authorization[7:]
    
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=["HS256"])
        chat_id = payload.get("sub")
        if not chat_id:
            raise ValueError("Missing subject claim")
        return int(chat_id)
    except jwt.ExpiredSignatureError:
        logger.warning("Token expired")
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError as e:
        logger.warning("Invalid token", extra={"error": str(e)})
        raise HTTPException(status_code=401, detail="Invalid token")


# Keep admin token verification for backward compatibility (if needed)
async def verify_admin_token(authorization: Optional[str] = Header(default=None)) -> None:
    """
    Проверяет Bearer-токен в заголовке Authorization.
    Используется для защиты эндпоинтов, доступных только администратору.
    """
    if not authorization:
        logger.warning("Authorization header missing")
        raise HTTPException(status_code=401, detail="Authorization header required")
    
    if not authorization.startswith("Bearer "):
        logger.warning(
            "Invalid token format",
            extra={"prefix": authorization[:10] if authorization else None}
        )
        raise HTTPException(status_code=401, detail="Invalid token format. Use 'Bearer <token>'")
    
    token = authorization[7:]
    
    if not token or token != settings.ADMIN_API_TOKEN:
        logger.warning("Invalid admin token attempt")
        raise HTTPException(status_code=401, detail="Invalid admin token")
    
    logger.debug("Admin token verified successfully")


def verify_pro_mode_access(
    project_repo: ProjectRepository = Depends(get_project_repo)
) -> Callable[[str], Awaitable[bool]]:
    """
    Dependency factory for checking Pro mode access.
    
    Returns a dependency function that checks if a project has Pro mode enabled.
    
    Args:
        project_repo: ProjectRepository instance (injected).
    
    Returns:
        Callable: Dependency function that takes project_id and checks is_pro_mode.
    """
    async def check_pro_mode(project_id: str) -> bool:
        """
        Check if project has Pro mode enabled.
        
        Args:
            project_id: UUID of the project to check.
        
        Returns:
            bool: True if Pro mode is enabled.
        
        Raises:
            HTTPException: If project not found or Pro mode not enabled.
        """
        is_pro = await project_repo.get_is_pro_mode(project_id)
        if not is_pro:
            logger.warning(
                "Pro mode access denied",
                extra={"project_id": project_id}
            )
            raise HTTPException(
                status_code=403,
                detail="Pro mode required. Upgrade your plan to access this feature."
            )
        return True
    
    return check_pro_mode
