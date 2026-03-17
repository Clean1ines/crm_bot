"""
Application lifespan management: database pool, orchestrator, and dependencies.
"""

import asyncpg
import httpx
from typing import Optional

from fastapi import FastAPI

from src.core.config import settings
from src.core.logging import get_logger
from src.services.orchestrator import OrchestratorService
from src.database.repositories.project_repository import ProjectRepository
from src.database.repositories.thread_repository import ThreadRepository
from src.database.repositories.queue_repository import QueueRepository
from src.database.repositories.event_repository import EventRepository

logger = get_logger(__name__)

pool: Optional[asyncpg.Pool] = None
orchestrator: Optional[OrchestratorService] = None


async def init_db():
    """Initialize database connection pool."""
    global pool
    db_url = settings.DATABASE_URL
    if not db_url:
        raise RuntimeError("DATABASE_URL is not set")
    
    pool = await asyncpg.create_pool(db_url, min_size=1, max_size=10, command_timeout=60)
    logger.info("Database pool initialized")


async def shutdown_db():
    """Close database connection pool."""
    global pool
    if pool:
        await pool.close()
        pool = None
        logger.info("Database pool closed")


async def _bootstrap_admin_project():
    """Create initial admin project if none exist (idempotent)."""
    if not settings.ADMIN_BOT_TOKEN or not pool:
        return
    
    async with pool.acquire() as conn:
        count = await conn.fetchval("SELECT COUNT(*) FROM projects")
        if count > 0:
            return
        
        project_id = await conn.fetchval("""
            INSERT INTO projects (id, name, owner_id, bot_token, system_prompt, template_slug, is_pro_mode)
            VALUES (gen_random_uuid(), 'Admin Project', '00000000-0000-0000-0000-000000000001', $1, 'Ты — полезный AI-ассистент.', 'support', true)
            RETURNING id
        """, settings.ADMIN_BOT_TOKEN)
        
        base_url = settings.RENDER_EXTERNAL_URL or settings.PUBLIC_URL
        if base_url:
            webhook_url = f"{base_url.rstrip('/')}/webhook/{project_id}"
            async with httpx.AsyncClient(timeout=30.0) as client:
                try:
                    resp = await client.post(
                        f"https://api.telegram.org/bot{settings.ADMIN_BOT_TOKEN}/setWebhook",
                        json={"url": webhook_url, "secret_token": settings.ADMIN_API_TOKEN[:32] if settings.ADMIN_API_TOKEN else None}
                    )
                    if resp.status_code == 200 and resp.json().get("ok"):
                        logger.info(f"Admin webhook set: {webhook_url}")
                except Exception as e:
                    logger.error(f"Failed to set admin webhook: {e}")


async def init_orchestrator():
    """Initialize OrchestratorService with all repository dependencies."""
    global pool, orchestrator
    if not pool:
        raise RuntimeError("Database pool not initialized")
    
    project_repo = ProjectRepository(pool)
    thread_repo = ThreadRepository(pool)
    queue_repo = QueueRepository(pool)
    event_repo = EventRepository(pool)  # NEW: event-sourced runtime
    
    orchestrator = OrchestratorService(
        db_conn=pool,
        project_repo=project_repo,
        thread_repo=thread_repo,
        queue_repo=queue_repo,
        event_repo=event_repo
    )
    logger.info("Orchestrator initialized with EventRepository")


async def lifespan(app: FastAPI):
    """FastAPI lifespan context manager: startup and shutdown."""
    global pool, orchestrator
    
    await init_db()
    await init_orchestrator()
    await _bootstrap_admin_project()
    
    yield
    
    await shutdown_db()
