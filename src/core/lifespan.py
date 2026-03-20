"""
Application lifespan management: database pool initialization and cleanup,
and global orchestrator/tool registry setup.

This module handles startup and shutdown events for the FastAPI application,
ensuring resources are properly initialized and released.
"""

import asyncio
import asyncpg
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.core.config import settings
from src.core.logging import get_logger
from src.services.orchestrator import OrchestratorService
from src.database.repositories.project_repository import ProjectRepository
from src.database.repositories.thread_repository import ThreadRepository
from src.database.repositories.queue_repository import QueueRepository
from src.database.repositories.memory_repository import MemoryRepository

logger = get_logger(__name__)

# Global instances (initialized in lifespan)
pool: asyncpg.Pool | None = None
orchestrator: OrchestratorService | None = None


async def init_db() -> asyncpg.Pool:
    """
    Initialize the database connection pool.
    
    Returns:
        asyncpg.Pool: Initialized connection pool.
    """
    if not settings.DATABASE_URL:
        raise RuntimeError("DATABASE_URL not configured")
    
    logger.info("Initializing database connection pool", extra={"url": settings.DATABASE_URL[:20] + "..."})
    
    pool = await asyncpg.create_pool(
        settings.DATABASE_URL,
        min_size=settings.DB_POOL_MIN_SIZE,
        max_size=settings.DB_POOL_MAX_SIZE,
        command_timeout=settings.DB_COMMAND_TIMEOUT
    )
    
    logger.info("Database pool initialized", extra={"min_size": settings.DB_POOL_MIN_SIZE, "max_size": settings.DB_POOL_MAX_SIZE})
    return pool


async def shutdown_db() -> None:
    """
    Close the database connection pool gracefully.
    """
    global pool
    if pool is not None:
        logger.info("Closing database connection pool")
        await pool.close()
        pool = None
        logger.info("Database pool closed")


def _register_builtin_tools(tool_registry, pool: asyncpg.Pool) -> None:
    """
    Register built-in tools in the ToolRegistry.
    
    This function should be called during application startup
    after repositories are initialized.
    
    Args:
        tool_registry: ToolRegistry instance to register tools in.
        pool: Database connection pool for repository initialization.
    """
    from src.tools.builtins import SearchKnowledgeTool, EscalateTool
    from src.database.repositories.knowledge_repository import KnowledgeRepository
    
    # Initialize repositories for tool wrappers
    knowledge_repo = KnowledgeRepository(pool)
    thread_repo = ThreadRepository(pool)
    queue_repo = QueueRepository(pool)
    project_repo = ProjectRepository(pool)
    
    # Register built-in tools
    tool_registry.register(SearchKnowledgeTool(knowledge_repo))
    logger.info("Registered SearchKnowledgeTool")
    
    tool_registry.register(EscalateTool(
        thread_repository=thread_repo,
        queue_repository=queue_repo,
        project_repository=project_repo
    ))
    logger.info("Registered EscalateTool")
    
    # Register extension tools (always available)
    from src.tools.http_tool import HTTPTool
    from src.tools.n8n_tool import N8NTool
    
    tool_registry.register(HTTPTool())
    logger.info("Registered HTTPTool")
    
    tool_registry.register(N8NTool())
    logger.info("Registered N8NTool")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage application lifespan: startup and shutdown.
    
    On startup:
    - Initialize database pool
    - Initialize ToolRegistry with built-in tools
    - Initialize all repositories (project, thread, queue, event, template, workflow, memory)
    - Register additional tools (CRM, ticket, telegram)
    - Create OrchestratorService with all dependencies
    
    On shutdown:
    - Close database pool
    
    Args:
        app: FastAPI application instance.
    
    Yields:
        None: Application runs during yield.
    """
    global pool, orchestrator
    
    # Startup
    logger.info("Application startup initiated")
    
    # Initialize database pool
    pool = await init_db()
    
    # Initialize ToolRegistry with built-in tools
    from src.tools import tool_registry
    _register_builtin_tools(tool_registry, pool)
    
    # Initialize all repositories for orchestrator
    project_repo = ProjectRepository(pool)
    thread_repo = ThreadRepository(pool)
    queue_repo = QueueRepository(pool)
    
    # Optional repositories (graceful degradation if migrations not applied)
    event_repo = None
    try:
        from src.database.repositories.event_repository import EventRepository
        event_repo = EventRepository(pool)
        logger.info("EventRepository initialized")
    except ImportError:
        logger.debug("EventRepository not available (migration 008 not applied yet)")
    
    template_repo = None
    try:
        from src.database.repositories.template_repository import TemplateRepository
        template_repo = TemplateRepository(pool)
        logger.info("TemplateRepository initialized")
    except ImportError:
        logger.debug("TemplateRepository not available (migration 009 not applied yet)")
    
    workflow_repo = None
    try:
        from src.database.repositories.workflow_repository import WorkflowRepository
        workflow_repo = WorkflowRepository(pool)
        logger.info("WorkflowRepository initialized")
    except ImportError:
        logger.debug("WorkflowRepository not available (migration 011 not applied yet)")
    
    # Memory repository (always available after migration 027)
    memory_repo = MemoryRepository(pool)
    logger.info("MemoryRepository initialized")
    
    # Register new CRM and ticket tools
    from src.tools.builtins import (
        CRMGetUserTool, CRMCreateUserTool, CRMCollectProfileTool,
        TicketCreateTool, TelegramSendMessageTool
    )
    
    # Note: CRMCollectProfileTool does not need db pool
    tool_registry.register(CRMCollectProfileTool())
    logger.info("Registered CRMCollectProfileTool")
    
    # Tools requiring pool
    tool_registry.register(CRMGetUserTool(pool))
    logger.info("Registered CRMGetUserTool")
    
    tool_registry.register(CRMCreateUserTool(pool))
    logger.info("Registered CRMCreateUserTool")
    
    tool_registry.register(TicketCreateTool(pool))
    logger.info("Registered TicketCreateTool")
    
    # TelegramSendMessageTool needs project_repo
    tool_registry.register(TelegramSendMessageTool(project_repo))
    logger.info("Registered TelegramSendMessageTool")
    
    # Create orchestrator with ALL dependencies
    orchestrator = OrchestratorService(
        db_conn=pool,
        project_repo=project_repo,
        thread_repo=thread_repo,
        queue_repo=queue_repo,
        event_repo=event_repo,
        template_repo=template_repo,
        workflow_repo=workflow_repo,
        tool_registry=tool_registry,
        memory_repo=memory_repo
    )
    
    logger.info(
        "Application startup complete",
        extra={
            "event_repo": event_repo is not None,
            "template_repo": template_repo is not None,
            "workflow_repo": workflow_repo is not None,
            "memory_repo": memory_repo is not None
        }
    )
    
    yield
    
    # Shutdown
    logger.info("Application shutdown initiated")
    await shutdown_db()
    logger.info("Application shutdown complete")
