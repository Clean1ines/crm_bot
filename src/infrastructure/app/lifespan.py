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

from src.infrastructure.config.settings import settings
from src.infrastructure.logging.logger import get_logger
from src.application.orchestration.conversation_orchestrator import ConversationOrchestrator
from src.infrastructure.llm.rag_service import RAGService
from src.infrastructure.db.repositories.project import ProjectTokenRepository, ProjectMemberRepository, ProjectQueryRepository, ProjectConfigurationRepository
from src.infrastructure.db.repositories.thread_repository import ThreadRepository
from src.infrastructure.db.repositories.queue_repository import QueueRepository
from src.infrastructure.db.repositories.memory_repository import MemoryRepository

logger = get_logger(__name__)

# Global instances (initialized in lifespan)
pool: asyncpg.Pool | None = None
orchestrator: ConversationOrchestrator | None = None


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


def _platform_owner_telegram_id() -> int | None:
    """Return configured global owner Telegram ID, preserving ADMIN_CHAT_ID fallback."""
    if not settings.BOOTSTRAP_PLATFORM_OWNER:
        return None

    configured_id = settings.PLATFORM_OWNER_TELEGRAM_ID or settings.ADMIN_CHAT_ID
    if not configured_id:
        return None
    return int(configured_id)


async def bootstrap_platform_owner(db_pool: asyncpg.Pool) -> str | None:
    """
    Ensure the platform owner is represented as a global platform user.

    This is intentionally identity-plane only: it never creates projects and never
    grants project roles. Project ownership still goes through project_members.
    """
    telegram_id = _platform_owner_telegram_id()
    if telegram_id is None:
        logger.info("Platform owner bootstrap skipped")
        return None

    async with db_pool.acquire() as conn:
        user_id = await conn.fetchval(
            """
            INSERT INTO users (telegram_id, full_name, is_platform_admin)
            VALUES ($1, $2, true)
            ON CONFLICT (telegram_id)
            DO UPDATE SET
                is_platform_admin = true,
                updated_at = NOW()
            RETURNING id
            """,
            telegram_id,
            "Platform Owner",
        )

        await conn.execute(
            """
            INSERT INTO auth_identities (user_id, provider, provider_id)
            VALUES ($1, 'telegram', $2)
            ON CONFLICT (provider, provider_id) DO NOTHING
            """,
            user_id,
            str(telegram_id),
        )

    logger.info(
        "Platform owner bootstrapped",
        extra={"user_id": str(user_id), "telegram_id": telegram_id},
    )
    return str(user_id)


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
    from src.infrastructure.db.repositories.knowledge_repository import KnowledgeRepository
    
    # Initialize repositories for tool wrappers
    knowledge_repo = KnowledgeRepository(pool)
    thread_repo = ThreadRepository(pool)
    queue_repo = QueueRepository(pool)
    project_tokens = ProjectTokenRepository(pool)
    project_members = ProjectMemberRepository(pool)
    
    # Create RAGService for enhanced search
    rag_service = RAGService(knowledge_repo)
    
    # Register built-in tools
    tool_registry.register(SearchKnowledgeTool(rag_service))
    logger.info("Registered SearchKnowledgeTool (with RAGService)")
    
    tool_registry.register(EscalateTool(
        thread_repository=thread_repo,
        queue_repository=queue_repo,
        project_members=project_members
    ))
    logger.info("Registered EscalateTool")
    
    # Register extension tools (always available)
    from src.tools.http_tool import HTTPTool
    
    tool_registry.register(HTTPTool())
    logger.info("Registered HTTPTool")
    logger.info("Registered N8NTool")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage application lifespan: startup and shutdown.
    
    On startup:
    - Initialize database pool
    - Initialize ToolRegistry with built-in tools
    - Initialize all repositories (project, thread, queue, event, template, memory)
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

    # Ensure the global platform owner exists before any control-plane work.
    await bootstrap_platform_owner(pool)
    
    # Initialize ToolRegistry with built-in tools
    from src.tools import tool_registry
    _register_builtin_tools(tool_registry, pool)
    
    # Initialize all repositories for orchestrator
    project_tokens = ProjectTokenRepository(pool)
    project_members = ProjectMemberRepository(pool)
    thread_repo = ThreadRepository(pool)
    queue_repo = QueueRepository(pool)
    
    from src.infrastructure.db.repositories.event_repository import EventRepository
    
    event_repo = EventRepository(pool)
    
    logger.info("Base repositories initialized (Event, Workflow)")
    
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
    tool_registry.register(TelegramSendMessageTool(project_tokens))
    logger.info("Registered TelegramSendMessageTool")
    
    # Create orchestrator with ALL dependencies
    orchestrator = ConversationOrchestrator(
        db_conn=pool,
        project_repo=ProjectQueryRepository(pool),
        thread_repo=thread_repo,
        queue_repo=queue_repo,
        event_repo=event_repo,
        tool_registry=tool_registry,
        memory_repo=memory_repo
    )
    
    logger.info(
        "Application startup complete",
        extra={
            "event_repo": event_repo is not None,
            "memory_repo": memory_repo is not None
        }
    )
    
    yield
    
    # Shutdown
    logger.info("Application shutdown initiated")
    await shutdown_db()
    logger.info("Application shutdown complete")
