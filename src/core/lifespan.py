"""
Application lifespan management: database pool initialization and cleanup,
and global orchestrator instance.
"""

import asyncpg
import httpx
from fastapi import FastAPI

from src.core.config import settings
from src.core.logging import get_logger
from src.services.orchestrator import OrchestratorService
from src.database.repositories.project_repository import ProjectRepository
from src.database.repositories.thread_repository import ThreadRepository
from src.database.repositories.queue_repository import QueueRepository

logger = get_logger(__name__)

# Global state
pool = None
orchestrator = None

async def init_db():
    """Initialize the database connection pool."""
    global pool
    db_url = settings.DATABASE_URL
    if not db_url:
        raise RuntimeError("DATABASE_URL is not set")
    pool = await asyncpg.create_pool(db_url, min_size=1, max_size=10)
    logger.info("Database pool created")

async def shutdown_db():
    """Close the database connection pool."""
    global pool
    if pool:
        await pool.close()
        logger.info("Database pool closed")

async def lifespan(app: FastAPI):
    """Manage application lifespan: startup and shutdown."""
    global pool, orchestrator
    await init_db()
    # Create repositories and orchestrator
    project_repo = ProjectRepository(pool)
    thread_repo = ThreadRepository(pool)
    queue_repo = QueueRepository(pool)
    orchestrator = OrchestratorService(
        db_conn=None,
        project_repo=project_repo,
        thread_repo=thread_repo,
        queue_repo=queue_repo
    )

    # On first run, if no projects exist and ADMIN_BOT_TOKEN is set,
    # create an admin project and set webhook.
    if settings.ADMIN_BOT_TOKEN:
        async with pool.acquire() as conn:
            count = await conn.fetchval("SELECT COUNT(*) FROM projects")
            if count == 0:
                logger.info("No projects found. Creating initial admin project with ADMIN_BOT_TOKEN.")
                # Insert project with a fixed owner_id (any UUID works)
                project_id = await conn.fetchval("""
                    INSERT INTO projects (id, name, owner_id, bot_token, system_prompt)
                    VALUES (gen_random_uuid(), 'Admin Project', '11111111-1111-1111-1111-111111111111', $1, 'Ты — полезный AI-ассистент.')
                    RETURNING id
                """, settings.ADMIN_BOT_TOKEN)

                # Set webhook for this project
                base_url = settings.RENDER_EXTERNAL_URL or settings.PUBLIC_URL
                if base_url:
                    webhook_url = f"{base_url.rstrip('/')}/webhook/{project_id}"
                    async with httpx.AsyncClient() as client:
                        try:
                            resp = await client.post(
                                f"https://api.telegram.org/bot{settings.ADMIN_BOT_TOKEN}/setWebhook",
                                json={"url": webhook_url}
                            )
                            if resp.status_code == 200:
                                logger.info(f"Webhook set to {webhook_url}")
                            else:
                                logger.error(f"Failed to set webhook: {resp.text}")
                        except Exception as e:
                            logger.error(f"Exception while setting webhook: {e}")
                else:
                    logger.warning("RENDER_EXTERNAL_URL not set, cannot set webhook automatically")

    yield
    await shutdown_db()
