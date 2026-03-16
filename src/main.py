"""
Main FastAPI application entry point.
Handles webhook endpoints and orchestrates the bot logic.
"""

import asyncio
import uuid
import asyncpg
from fastapi import FastAPI, Request, HTTPException
import httpx

from src.core.config import settings
from src.core.logging import configure_logging, CorrelationIdMiddleware, get_logger
from src.services.orchestrator import OrchestratorService
from src.database.repositories.project_repository import ProjectRepository
from src.database.repositories.thread_repository import ThreadRepository
from src.database.repositories.queue_repository import QueueRepository
from src.admin_handlers import handle_admin_command

# Configure structured logging
configure_logging()
logger = get_logger(__name__)

# Global variables for DB pool and services
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
    await init_db()
    # Create repositories and orchestrator
    project_repo = ProjectRepository(pool)
    thread_repo = ThreadRepository(pool)
    queue_repo = QueueRepository(pool)
    global orchestrator
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

# FastAPI application with lifespan
app = FastAPI(title=settings.PROJECT_NAME, lifespan=lifespan)

# Add logging middleware
app.add_middleware(CorrelationIdMiddleware)

@app.post("/webhook/{project_id}")
async def telegram_webhook(project_id: str, request: Request):
    """
    Unified endpoint for receiving Telegram webhooks.
    Processes incoming messages and sends responses via Telegram API.
    """
    try:
        # Get the update from Telegram
        update = await request.json()
        logger.info(f"Received update from project {project_id}: {update}")

        # Check if it's a message
        if "message" not in update:
            # Ignore other update types (e.g., callback_query)
            return {"ok": True}

        message = update["message"]
        chat_id = message["chat"]["id"]
        text = message.get("text")
        if not text:
            # Ignore non-text messages
            return {"ok": True}

        # Get bot token for this project via repository
        project_repo = ProjectRepository(pool)
        bot_token = await project_repo.get_bot_token(project_id)
        if not bot_token:
            logger.error(f"Bot token not found for project {project_id}")
            raise HTTPException(status_code=404, detail="Project not found or bot token missing")

        # Check if sender is admin and message is a command
        if str(chat_id) == settings.ADMIN_CHAT_ID and text.startswith("/"):
            # Handle admin command
            result = await handle_admin_command(text, pool)
            # Send response via the same bot
            send_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            payload = {"chat_id": chat_id, "text": result}
            async with httpx.AsyncClient() as client:
                await client.post(send_url, json=payload)
            return {"ok": True}

        # Otherwise, continue with normal message processing
        response_text = await orchestrator.process_message(
            project_id=project_id,
            chat_id=chat_id,
            text=text
        )

        # Send the response via Telegram Bot API
        send_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": response_text,
            # optional: parse_mode, reply_to_message_id, etc.
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(send_url, json=payload)
            if resp.status_code != 200:
                logger.error(f"Failed to send message: {resp.text}")

        return {"ok": True}

    except Exception as e:
        logger.exception("Error processing webhook")
        raise HTTPException(status_code=500, detail="Internal server error")

# For local development, you can run with uvicorn
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
