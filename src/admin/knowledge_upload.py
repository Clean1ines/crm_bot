"""
Admin bot handler for uploading knowledge base files.

Processes Telegram document uploads:
- downloads file from Telegram
- extracts text (PDF/TXT)
- chunks text
- generates embeddings
- stores in knowledge_base
"""

from typing import Tuple, Optional, List

from src.core.logging import get_logger
from src.core.config import settings
from src.services.chunker import ChunkerService
from src.services.embedding_service import embed_text
from src.database.repositories.knowledge_repository import KnowledgeRepository
from src.admin.handlers import _get_data, _clear_state, _get_project_menu_keyboard

import aiohttp

logger = get_logger(__name__)


async def _download_file(file_path: str) -> bytes:
    """
    Download file from Telegram servers.

    Args:
        file_path: path returned by Telegram getFile

    Returns:
        file bytes
    """
    url = f"https://api.telegram.org/file/bot{settings.ADMIN_BOT_TOKEN}/{file_path}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                logger.error("Failed to download file", extra={"status": resp.status})
                raise ValueError("Failed to download file from Telegram")
            return await resp.read()


async def _get_file_path(file_id: str) -> str:
    """
    Get file_path from Telegram API.

    Args:
        file_id: Telegram file_id

    Returns:
        file_path string
    """
    url = f"https://api.telegram.org/bot{settings.ADMIN_BOT_TOKEN}/getFile"
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json={"file_id": file_id}) as resp:
            data = await resp.json()
            if not data.get("ok"):
                logger.error("getFile failed", extra={"response": data})
                raise ValueError("Telegram getFile failed")
            return data["result"]["file_path"]


async def handle_knowledge_upload(chat_id: str, message: dict, pool) -> Tuple[str, Optional[object]]:
    """
    Handle knowledge file upload from Telegram document message.

    Flow:
    - extract file_id
    - download file
    - chunk text
    - generate embeddings
    - store in DB

    Args:
        chat_id: admin chat id
        message: full Telegram message dict (must contain document)
        pool: asyncpg pool

    Returns:
        (response_text, keyboard)
    """
    data = await _get_data(chat_id)
    project_id = data.get("project_id")

    if not project_id:
        logger.error("Project ID missing in state", extra={"chat_id": chat_id})
        await _clear_state(chat_id)
        return "❌ Ошибка: проект не указан.", None

    document = message.get("document")
    if not document:
        logger.warning("No document in message", extra={"chat_id": chat_id})
        return "❌ Пожалуйста, отправьте файл (.pdf или .txt).", None

    file_id = document.get("file_id")
    filename = document.get("file_name", "unknown")

    logger.info("Starting knowledge upload", extra={
        "project_id": project_id,
        "filename": filename
    })

    try:
        # 1. Download file
        file_path = await _get_file_path(file_id)
        file_bytes = await _download_file(file_path)

        logger.debug("File downloaded", extra={"size": len(file_bytes)})

        # 2. Chunking
        chunker = ChunkerService()
        chunks: List[str] = await chunker.process_file(file_bytes, filename)

        if not chunks:
            logger.warning("No chunks generated", extra={"filename": filename})
            return "⚠️ Не удалось извлечь текст из файла.", None

        logger.info("Chunks created", extra={"count": len(chunks)})

        # 3. Embeddings
        embeddings = []
        for i, chunk in enumerate(chunks):
            emb = await embed_text(chunk)
            embeddings.append(emb)

            if i % 10 == 0:
                logger.debug("Embedding progress", extra={"processed": i})

        # 4. Save to DB
        repo = KnowledgeRepository(pool)
        await repo.add_knowledge_batch(project_id, chunks, embeddings)

        logger.info("Knowledge base updated", extra={
            "project_id": project_id,
            "chunks": len(chunks)
        })

        await _clear_state(chat_id)

        return (
            f"✅ Загружено {len(chunks)} чанков.\nБаза знаний обновлена.",
            await _get_project_menu_keyboard(project_id, pool)
        )

    except Exception as e:
        logger.exception("Knowledge upload failed", extra={
            "project_id": project_id,
            "filename": filename
        })
        await _clear_state(chat_id)
        return (
            "❌ Ошибка при обработке файла. Попробуйте другой файл или проверьте формат.",
            await _get_project_menu_keyboard(project_id, pool)
        )
