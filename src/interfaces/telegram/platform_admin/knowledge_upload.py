"""
Platform admin bot handler for uploading knowledge base files.
"""

import aiohttp

from src.infrastructure.config.settings import settings
from src.infrastructure.db.repositories.knowledge_repository import KnowledgeRepository
from src.infrastructure.llm.chunker import ChunkerService
from src.infrastructure.llm.embedding_service import embed_text
from src.infrastructure.logging.logger import get_logger
from src.interfaces.telegram.platform_admin.handlers import (
    _clear_state,
    _get_data,
    _get_project_menu_keyboard,
)

logger = get_logger(__name__)


async def _download_file(file_path: str) -> bytes:
    url = f"https://api.telegram.org/file/bot{settings.ADMIN_BOT_TOKEN}/{file_path}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                logger.error("Failed to download file", extra={"status": resp.status})
                raise ValueError("Failed to download file from Telegram")
            return await resp.read()


async def _get_file_path(file_id: str) -> str:
    url = f"https://api.telegram.org/bot{settings.ADMIN_BOT_TOKEN}/getFile"
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json={"file_id": file_id}) as resp:
            data = await resp.json()
            if not data.get("ok"):
                logger.error("getFile failed", extra={"response": data})
                raise ValueError("Telegram getFile failed")
            return data["result"]["file_path"]


async def handle_knowledge_upload(
    chat_id: str, message: dict, pool
) -> tuple[str, object | None]:
    data = await _get_data(chat_id)
    project_id = data.get("project_id")

    if not project_id:
        logger.error("Project ID missing in state", extra={"chat_id": chat_id})
        await _clear_state(chat_id)
        return "Ошибка: проект не указан.", None

    document = message.get("document")
    if not document:
        logger.warning("No document in message", extra={"chat_id": chat_id})
        return "Пожалуйста, отправьте файл (.pdf или .txt).", None

    file_id = document.get("file_id")
    filename = document.get("file_name", "unknown")

    logger.info(
        "Starting knowledge upload",
        extra={"project_id": project_id, "filename": filename},
    )

    try:
        file_path = await _get_file_path(file_id)
        file_bytes = await _download_file(file_path)

        chunker = ChunkerService()
        chunks: list[str] = await chunker.process_file(file_bytes, filename)
        if not chunks:
            logger.warning("No chunks generated", extra={"filename": filename})
            return "Не удалось извлечь текст из файла.", None

        embeddings = []
        for index, chunk in enumerate(chunks):
            emb = await embed_text(chunk)
            embeddings.append(emb)
            if index % 10 == 0:
                logger.debug("Embedding progress", extra={"processed": index})

        repo = KnowledgeRepository(pool)
        await repo.add_knowledge_batch(
            str(project_id),
            [
                {"content": chunk, "embedding": embedding}
                for chunk, embedding in zip(chunks, embeddings, strict=True)
            ],
        )

        logger.info(
            "Knowledge base updated",
            extra={"project_id": project_id, "chunks": len(chunks)},
        )
        await _clear_state(chat_id)
        return (
            f"Загружено {len(chunks)} чанков.\nБаза знаний обновлена.",
            await _get_project_menu_keyboard(str(project_id), pool),
        )
    except Exception as exc:
        logger.exception(
            "Knowledge upload failed",
            extra={
                "chat_id": chat_id,
                "project_id": project_id,
                "filename": filename,
                "error": str(exc),
                "error_type": type(exc).__name__,
                "policy": "safe_user_fallback",
            },
        )
        await _clear_state(chat_id)
        return (
            "Ошибка при обработке файла. Попробуйте другой файл или проверьте формат.",
            await _get_project_menu_keyboard(str(project_id), pool),
        )
