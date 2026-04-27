"""
FastAPI composition root.

This module wires the concrete application:
- infrastructure resources
- repositories/adapters
- tool registry
- agent runtime
- application orchestrator

Infrastructure modules must stay generic and must not import src.agent.
"""

from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI

from src.agent.graph import create_agent
from src.application.orchestration.conversation_orchestrator import (
    ConversationOrchestrator,
)
from src.infrastructure.app.resources import (
    bootstrap_platform_owner,
    init_db,
    shutdown_db,
)
from src.infrastructure.config.settings import settings
from src.infrastructure.db.repositories.event_repository import EventRepository
from src.infrastructure.db.repositories.knowledge_repository import KnowledgeRepository
from src.infrastructure.db.repositories.memory_repository import MemoryRepository
from src.infrastructure.db.repositories.project import (
    ProjectMemberRepository,
    ProjectQueryRepository,
    ProjectTokenRepository,
)
from src.infrastructure.db.repositories.queue_repository import QueueRepository
from src.infrastructure.db.repositories.thread.lifecycle import (
    ThreadLifecycleRepository,
)
from src.infrastructure.db.repositories.thread.messages import ThreadMessageRepository
from src.infrastructure.db.repositories.thread.read import ThreadReadRepository
from src.infrastructure.db.repositories.thread.runtime_state import (
    ThreadRuntimeStateRepository,
)
from src.infrastructure.llm.rag_service import RAGService
from src.infrastructure.llm.query_expander import GroqQueryExpander
from src.infrastructure.logging.logger import get_logger
from src.tools import tool_registry
from src.tools.builtins import (
    CRMCollectProfileTool,
    CRMCreateUserTool,
    CRMGetUserTool,
    EscalateTool,
    SearchKnowledgeTool,
    TelegramSendMessageTool,
    TicketCreateTool,
)
from src.tools.http_tool import HTTPTool

logger = get_logger(__name__)

pool: asyncpg.Pool | None = None
orchestrator: ConversationOrchestrator | None = None


def register_builtin_tools(db_pool: asyncpg.Pool) -> None:
    """
    Register all runtime tools.

    This belongs to composition, not infrastructure, because it wires DB-backed
    adapters, LLM services, and the process-wide tool registry together.
    """
    knowledge_repo = KnowledgeRepository(db_pool)
    thread_lifecycle_repo = ThreadLifecycleRepository(db_pool)
    queue_repo = QueueRepository(db_pool)
    project_tokens = ProjectTokenRepository(db_pool)
    project_members = ProjectMemberRepository(db_pool)

    rag_service = RAGService(knowledge_repo, query_expander=GroqQueryExpander())

    tool_registry.register(SearchKnowledgeTool(rag_service))
    logger.info("Registered SearchKnowledgeTool")

    tool_registry.register(
        EscalateTool(
            thread_lifecycle_repo=thread_lifecycle_repo,
            queue_repository=queue_repo,
            project_members=project_members,
        )
    )
    logger.info("Registered EscalateTool")

    tool_registry.register(HTTPTool())
    logger.info("Registered HTTPTool")

    tool_registry.register(CRMCollectProfileTool())
    logger.info("Registered CRMCollectProfileTool")

    tool_registry.register(CRMGetUserTool(db_pool))
    logger.info("Registered CRMGetUserTool")

    tool_registry.register(CRMCreateUserTool(db_pool))
    logger.info("Registered CRMCreateUserTool")

    tool_registry.register(TicketCreateTool(db_pool))
    logger.info("Registered TicketCreateTool")

    tool_registry.register(TelegramSendMessageTool(project_tokens))
    logger.info("Registered TelegramSendMessageTool")


def build_orchestrator(db_pool: asyncpg.Pool) -> ConversationOrchestrator:
    """
    Build the application orchestrator with concrete adapters.

    The application layer receives narrow thread repositories by injection.
    """
    thread_lifecycle_repo = ThreadLifecycleRepository(db_pool)
    thread_message_repo = ThreadMessageRepository(db_pool)
    thread_read_repo = ThreadReadRepository(db_pool)
    thread_runtime_state_repo = ThreadRuntimeStateRepository(db_pool)

    queue_repo = QueueRepository(db_pool)
    event_repo = EventRepository(db_pool)
    memory_repo = MemoryRepository(db_pool)

    return ConversationOrchestrator(
        db_conn=db_pool,
        project_repo=ProjectQueryRepository(db_pool),
        thread_lifecycle_repo=thread_lifecycle_repo,
        thread_message_repo=thread_message_repo,
        thread_runtime_state_repo=thread_runtime_state_repo,
        thread_read_repo=thread_read_repo,
        queue_repo=queue_repo,
        event_repo=event_repo,
        tool_registry=tool_registry,
        memory_repo=memory_repo,
        logger=logger,
        agent_factory=create_agent,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI startup/shutdown composition boundary.
    """
    global pool, orchestrator

    logger.info("Application startup initiated")

    pool = await init_db(settings=settings, logger=logger)
    await bootstrap_platform_owner(pool, settings=settings, logger=logger)

    register_builtin_tools(pool)
    orchestrator = build_orchestrator(pool)

    logger.info("Application startup complete")

    try:
        yield
    finally:
        logger.info("Application shutdown initiated")
        await shutdown_db(pool, logger=logger)
        pool = None
        orchestrator = None
        logger.info("Application shutdown complete")
