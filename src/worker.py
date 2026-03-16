"""
Worker process for handling background tasks from the execution queue.
Currently supports:
- notify_manager: sends an inline keyboard notification to the manager.
"""

import asyncio
import signal
import asyncpg
import httpx

from src.core.config import settings
from src.core.logging import get_logger
from src.database.repositories.queue_repository import QueueRepository

logger = get_logger(__name__)

shutdown_event = asyncio.Event()

def handle_sigterm():
    """Signal handler for graceful shutdown."""
    logger.info("Received SIGTERM, shutting down...")
    shutdown_event.set()

async def worker_loop(pool):
    """
    Main worker loop: continuously claim jobs from the queue and process them.
    """
    queue_repo = QueueRepository(pool)

    while not shutdown_event.is_set():
        try:
            job = await queue_repo.claim_job("worker-1")
            if not job:
                await asyncio.sleep(1)
                continue

            logger.info(f"Processing job {job['id']} of type {job['task_type']}")

            if job["task_type"] == "notify_manager":
                payload = job.get("payload") or {}
                thread_id = payload.get("thread_id")
                chat_id = payload.get("chat_id")
                message = payload.get("message")

                # Get manager bot settings from config
                manager_bot_token = settings.MANAGER_BOT_TOKEN
                manager_chat_id = settings.MANAGER_CHAT_ID
                if not manager_bot_token or not manager_chat_id:
                    logger.error("MANAGER_BOT_TOKEN or MANAGER_CHAT_ID not set")
                    await queue_repo.complete_job(job["id"], success=False)
                    continue

                # Build inline keyboard markup
                reply_markup = {
                    "inline_keyboard": [[{
                        "text": "✏️ Ответить",
                        "callback_data": f"reply:{thread_id}"
                    }]]
                }

                # Send notification to manager
                url = f"https://api.telegram.org/bot{manager_bot_token}/sendMessage"
                params = {
                    "chat_id": int(manager_chat_id),
                    "text": f"Новое сообщение (thread {thread_id}):\n\n{message}",
                    "reply_markup": reply_markup
                }
                try:
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        resp = await client.post(url, json=params)
                        resp.raise_for_status()
                    logger.info(f"Manager notified for job {job['id']} (thread {thread_id})")
                    await queue_repo.complete_job(job["id"], success=True)
                except Exception as e:
                    logger.error(f"Failed to send manager notification: {e}")
                    await queue_repo.complete_job(job["id"], success=False)
            else:
                logger.warning(f"Unknown task type: {job['task_type']}")
                await queue_repo.complete_job(job["id"], success=False)

        except Exception as e:
            logger.exception("Error in worker loop")

    logger.info("Worker shutting down")

async def main():
    """
    Main entry point: set up signal handlers, create database pool, and run worker loop.
    """
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, handle_sigterm)

    db_url = settings.DATABASE_URL
    if not db_url:
        raise RuntimeError("DATABASE_URL not set")

    pool = await asyncpg.create_pool(db_url, min_size=1, max_size=10)
    try:
        await worker_loop(pool)
    finally:
        await pool.close()
        logger.info("Database pool closed")

if __name__ == "__main__":
    asyncio.run(main())
