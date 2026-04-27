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

from src.infrastructure.logging.logger import get_logger
from src.infrastructure.config.settings import settings
from src.infrastructure.db.repositories.project import ProjectRepository
from src.infrastructure.db.repositories.thread.lifecycle import ThreadLifecycleRepository
from src.infrastructure.db.repositories.thread.messages import ThreadMessageRepository
from src.infrastructure.db.repositories.thread.read import ThreadReadRepository
from src.infrastructure.db.repositories.thread.runtime_state import ThreadRuntimeStateRepository
from src.infrastructure.db.repositories.client_repository import ClientRepository
from src.infrastructure.db.repositories.queue_repository import QueueRepository
from src.infrastructure.db.repositories.event_repository import EventRepository
from src.infrastructure.db.repositories.user_repository import UserRepository
from src.infrastructure.db.repositories.metrics_repository import MetricsRepository
from src.infrastructure.db.repositories.memory_repository import MemoryRepository
from src.application.services.client_query_service import ClientQueryService
from src.application.services.project_command_service import ProjectCommandService
from src.application.services.project_query_service import ProjectQueryService
from src.application.services.project_service import ProjectAccessService
from src.application.services.thread_command_service import ThreadCommandService
from src.application.services.thread_query_service import ThreadQueryService
from src.infrastructure.redis.client import get_redis_client

import src.interfaces.composition.fastapi_lifespan

logger = get_logger(__name__)


def get_pool() -> Any:
    """
    Return the global database connection pool.
    
    Raises:
        RuntimeError: If pool is not initialized (called before lifespan startup).
    
    Returns:
        asyncpg.Pool: The global database connection pool.
    """
    if src.interfaces.composition.fastapi_lifespan.pool is None:
        logger.error("Database pool requested before initialization")
        raise RuntimeError("Database pool not initialized")
    return src.interfaces.composition.fastapi_lifespan.pool


def get_orchestrator() -> Any:
    """
    Return the global orchestrator instance.
    
    Raises:
        RuntimeError: If orchestrator is not initialized.
    
    Returns:
        OrchestratorService: The global orchestrator instance.
    """
    if src.interfaces.composition.fastapi_lifespan.orchestrator is None:
        logger.error("Orchestrator requested before initialization")
        raise RuntimeError("Orchestrator not initialized")
    return src.interfaces.composition.fastapi_lifespan.orchestrator


def get_project_repo(pool: Any = Depends(get_pool)) -> ProjectRepository:
    """
    Return a new ProjectRepository instance.
    
    Args:
        pool: Database connection pool (injected via Depends).
    
    Returns:
        ProjectRepository: Repository for project-level data access.
    """
    return ProjectRepository(pool)


def get_project_service(
    project_repo: ProjectRepository = Depends(get_project_repo),
) -> ProjectAccessService:
    """
    Return the application service for project control-plane operations.
    """
    return ProjectAccessService(project_repo)


def get_event_repo(pool: Any = Depends(get_pool)) -> EventRepository:
    """
    Return a new EventRepository instance.
    
    Args:
        pool: Database connection pool (injected via Depends).
    
    Returns:
        EventRepository: Repository for event-sourced data access.
    """
    return EventRepository(pool)


def get_project_query_service(
    project_repo: ProjectRepository = Depends(get_project_repo),
    project_service: ProjectAccessService = Depends(get_project_service),
    event_repo: EventRepository = Depends(get_event_repo),
) -> ProjectQueryService:
    """Return the application query service for project control-plane reads."""
    return ProjectQueryService(project_repo, project_service, event_repo)


def get_project_command_service(
    project_repo: ProjectRepository = Depends(get_project_repo),
    project_service: ProjectAccessService = Depends(get_project_service),
    project_query_service: ProjectQueryService = Depends(get_project_query_service),
) -> ProjectCommandService:
    """Return the application command service for project control-plane writes."""
    return ProjectCommandService(project_repo, project_service, project_query_service)


def get_client_repo(pool: Any = Depends(get_pool)) -> ClientRepository:
    """
    Return a new ClientRepository instance.
    """
    return ClientRepository(pool)


def get_queue_repo(pool: Any = Depends(get_pool)) -> QueueRepository:
    """
    Return a new QueueRepository instance.
    
    Args:
        pool: Database connection pool (injected via Depends).
    
    Returns:
        QueueRepository: Repository for background job queue operations.
    """
    return QueueRepository(pool)


def get_user_repository(pool: Any = Depends(get_pool)) -> UserRepository:
    """
    Return a new UserRepository instance.
    
    Args:
        pool: Database connection pool (injected via Depends).
    
    Returns:
        UserRepository: Repository for user and auth identity operations.
    """
    return UserRepository(pool)


def get_metrics_repository(pool: Any = Depends(get_pool)) -> MetricsRepository:
    """
    Return a new MetricsRepository instance.
    
    Args:
        pool: Database connection pool (injected via Depends).
    
    Returns:
        MetricsRepository: Repository for thread and project metrics.
    """
    return MetricsRepository(pool)


def get_thread_lifecycle_repo(pool: Any = Depends(get_pool)) -> ThreadLifecycleRepository:
    """Return repository for thread lifecycle operations."""
    return ThreadLifecycleRepository(pool)


def get_thread_message_repo(pool: Any = Depends(get_pool)) -> ThreadMessageRepository:
    """Return repository for thread message operations."""
    return ThreadMessageRepository(pool)


def get_thread_read_repo(pool: Any = Depends(get_pool)) -> ThreadReadRepository:
    """Return repository for thread read models."""
    return ThreadReadRepository(pool)


def get_thread_runtime_state_repo(pool: Any = Depends(get_pool)) -> ThreadRuntimeStateRepository:
    """Return repository for thread runtime state operations."""
    return ThreadRuntimeStateRepository(pool)


def get_memory_repository(pool: Any = Depends(get_pool)) -> MemoryRepository:
    """
    Return a new MemoryRepository instance.
    
    Args:
        pool: Database connection pool (injected via Depends).
    
    Returns:
        MemoryRepository: Repository for user memory (long-term facts).
    """
    return MemoryRepository(pool)


def get_client_query_service(
    client_repo: ClientRepository = Depends(get_client_repo),
    thread_read_repo: ThreadReadRepository = Depends(get_thread_read_repo),
    memory_repo: MemoryRepository = Depends(get_memory_repository),
) -> ClientQueryService:
    """Return the application read service for client-focused queries."""
    return ClientQueryService(client_repo, thread_read_repo, memory_repo)


def get_thread_query_service(
    thread_read_repo: ThreadReadRepository = Depends(get_thread_read_repo),
    thread_message_repo: ThreadMessageRepository = Depends(get_thread_message_repo),
    thread_runtime_state_repo: ThreadRuntimeStateRepository = Depends(get_thread_runtime_state_repo),
    event_repo: EventRepository = Depends(get_event_repo),
    memory_repo: MemoryRepository = Depends(get_memory_repository),
) -> ThreadQueryService:
    """Return the application read service for thread-focused queries."""
    return ThreadQueryService(
        thread_read_repo=thread_read_repo,
        thread_message_repo=thread_message_repo,
        thread_runtime_state_repo=thread_runtime_state_repo,
        event_repo=event_repo,
        memory_repo=memory_repo,
    )


def get_thread_command_service(
    thread_lifecycle_repo: ThreadLifecycleRepository = Depends(get_thread_lifecycle_repo),
    memory_repo: MemoryRepository = Depends(get_memory_repository),
) -> ThreadCommandService:
    """Return the application write service for thread-focused mutations."""
    return ThreadCommandService(thread_lifecycle_repo, memory_repo)


def get_tool_registry() -> Any:
    """
    Return the global ToolRegistry singleton instance.
    
    This dependency provides access to the ToolRegistry for dynamic
    tool execution from API endpoints.
    
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


async def get_current_user_id(authorization: Optional[str] = Header(default=None)) -> str:
    """
    Dependency that validates JWT and returns the user's UUID.
    
    The JWT must contain a 'sub' claim with the user's UUID.
    
    Args:
        authorization: Bearer token from Authorization header.
    
    Returns:
        str: User ID (UUID) extracted from the token.
    
    Raises:
        HTTPException: If token is missing, invalid, or expired.
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
        user_id = payload.get("sub")
        if not user_id:
            raise ValueError("Missing subject claim")
        # Ensure it's a string (UUID)
        return str(user_id)
    except jwt.ExpiredSignatureError:
        logger.warning("Token expired")
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError as e:
        logger.warning("Invalid token", extra={"error": str(e)})
        raise HTTPException(status_code=401, detail="Invalid token")


async def require_platform_admin(
    current_user_id: str = Depends(get_current_user_id),
    user_repo: UserRepository = Depends(get_user_repository),
) -> str:
    """
    Require the authenticated user to have global platform administration rights.

    This guard is for control-plane/platform operations only. Project-level
    permissions must continue to use project_members via ProjectAccessService.
    """
    if await user_repo.is_platform_admin(current_user_id):
        return current_user_id

    logger.warning(
        "Platform admin access denied",
        extra={"user_id": current_user_id},
    )
    raise HTTPException(status_code=403, detail="Platform admin required")


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
        try:
            is_pro = await project_repo.get_is_pro_mode(project_id)
        except Exception as exc:
            logger.warning(
                "Pro mode guard failed closed",
                extra={
                    "project_id": project_id,
                    "error_type": type(exc).__name__,
                },
            )
            raise HTTPException(
                status_code=503,
                detail="Project runtime guard unavailable",
            ) from exc

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
