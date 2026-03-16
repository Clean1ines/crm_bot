import asyncio
import os
import logging
import asyncpg
from fastapi import FastAPI, Request, HTTPException
import httpx
from src.services.orchestrator import OrchestratorService
from src.database.repositories.project_repository import ProjectRepository
from src.database.repositories.thread_repository import ThreadRepository

# Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Глобальные переменные для пула и сервисов
pool = None
orchestrator = None

async def init_db():
    """Инициализирует пул соединений с БД."""
    global pool
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL is not set")
    pool = await asyncpg.create_pool(db_url, min_size=1, max_size=10)
    logger.info("Database pool created")

async def shutdown_db():
    """Закрывает пул соединений."""
    global pool
    if pool:
        await pool.close()
        logger.info("Database pool closed")

async def lifespan(app: FastAPI):
    """Управляет жизненным циклом приложения."""
    await init_db()
    # Создаём репозитории и оркестратор
    project_repo = ProjectRepository(pool)
    thread_repo = ThreadRepository(pool)
    global orchestrator
    orchestrator = OrchestratorService(db_conn=None, project_repo=project_repo, thread_repo=thread_repo)
    yield
    await shutdown_db()

# FastAPI приложение с lifespan
app = FastAPI(title="MRAK-OS CRM Bot API", lifespan=lifespan)

@app.post("/webhook/{project_id}")
async def telegram_webhook(project_id: str, request: Request):
    """
    Единый эндпоинт для приёма вебхуков от Telegram.
    Обрабатывает входящие сообщения и отправляет ответ через API.
    """
    try:
        # Получаем обновление от Telegram
        update = await request.json()
        logger.info(f"Received update from project {project_id}: {update}")

        # Проверяем, что это сообщение
        if "message" not in update:
            # Игнорируем другие типы обновлений (например, callback_query)
            return {"ok": True}

        message = update["message"]
        chat_id = message["chat"]["id"]
        text = message.get("text")
        if not text:
            # Если нет текста (например, стикер) – ничего не делаем
            return {"ok": True}

        # Получаем токен бота для этого проекта через репозиторий
        project_repo = ProjectRepository(pool)
        bot_token = await project_repo.get_bot_token(project_id)
        if not bot_token:
            logger.error(f"Bot token not found for project {project_id}")
            raise HTTPException(status_code=404, detail="Project not found or bot token missing")

        # Вызываем оркестратор для генерации ответа
        response_text = await orchestrator.process_message(
            project_id=project_id,
            chat_id=chat_id,
            text=text
        )

        # Отправляем ответ через Telegram Bot API
        send_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": response_text,
            # можно добавить parse_mode, reply_to_message_id и т.д.
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(send_url, json=payload)
            if resp.status_code != 200:
                logger.error(f"Failed to send message: {resp.text}")

        return {"ok": True}

    except Exception as e:
        logger.exception("Error processing webhook")
        raise HTTPException(status_code=500, detail="Internal server error")

# Для локального запуска можно оставить точку входа через uvicorn
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
