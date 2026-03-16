import asyncio
import os
import signal
import logging
import asyncpg
import httpx
from src.database.repositories.queue_repository import QueueRepository

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

shutdown_event = asyncio.Event()

def handle_sigterm():
    logger.info("Received SIGTERM, shutting down...")
    shutdown_event.set()

async def worker_loop(pool):
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

                # Получаем настройки менеджера из окружения
                manager_bot_token = os.getenv("MANAGER_BOT_TOKEN")
                manager_chat_id = os.getenv("MANAGER_CHAT_ID")
                if not manager_bot_token or not manager_chat_id:
                    logger.error("MANAGER_BOT_TOKEN or MANAGER_CHAT_ID not set")
                    await queue_repo.complete_job(job["id"], success=False)
                    continue

                # Отправляем уведомление менеджеру
                url = f"https://api.telegram.org/bot{manager_bot_token}/sendMessage"
                params = {
                    "chat_id": int(manager_chat_id),
                    "text": f"Новое сообщение (thread {thread_id}):\n\n{message}"
                }
                try:
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        resp = await client.post(url, json=params)
                        resp.raise_for_status()
                    logger.info(f"Manager notified for job {job['id']}")
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
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, handle_sigterm)

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL not set")

    pool = await asyncpg.create_pool(db_url, min_size=1, max_size=10)
    try:
        await worker_loop(pool)
    finally:
        await pool.close()

if __name__ == "__main__":
    asyncio.run(main())
