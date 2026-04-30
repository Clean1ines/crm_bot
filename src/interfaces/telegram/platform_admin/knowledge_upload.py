"""
Platform admin bot handler for uploading knowledge base files.
"""

import aiohttp
from telegram import InlineKeyboardMarkup

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

DocumentPayload = dict[str, object]
UploadResult = tuple[str, InlineKeyboardMarkup | None]


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


async def _project_id_for_upload(chat_id: str) -> str | None:
    data = await _get_data(chat_id)
    project_id = data.get("project_id")
    if project_id is None:
        return None
    return str(project_id)


def _missing_project_response() -> UploadResult:
    return "Ошибка: проект не указан.", None


def _missing_document_response() -> UploadResult:
    return "Пожалуйста, отправьте файл (.pdf, .txt, .md или .json).", None


def _invalid_document_response() -> UploadResult:
    return (
        "Пожалуйста, отправьте файл (.pdf, .txt, .md или .json).",
        None,
    )


def _missing_file_id_response() -> UploadResult:
    return (
        "Не удалось определить файл. Попробуйте ещё раз.",
        None,
    )


def _no_chunks_response() -> UploadResult:
    return "Не удалось извлечь текст из файла.", None


async def _validate_document(
    *,
    chat_id: str,
    message: dict[str, object],
) -> tuple[DocumentPayload | None, UploadResult | None]:
    document = message.get("document")
    if not document:
        logger.warning("No document in message", extra={"chat_id": chat_id})
        return None, _missing_document_response()

    if not isinstance(document, dict):
        logger.warning(
            "Document payload has unexpected shape", extra={"chat_id": chat_id}
        )
        return None, _invalid_document_response()

    file_id = str(document.get("file_id") or "")
    if not file_id:
        logger.warning("Document payload missing file_id", extra={"chat_id": chat_id})
        return None, _missing_file_id_response()

    return document, None


def _document_metadata(document: DocumentPayload) -> tuple[str, str]:
    return str(document["file_id"]), str(document.get("file_name") or "unknown")


async def _chunk_document(file_id: str, filename: str) -> list[str]:
    file_path = await _get_file_path(file_id)
    file_bytes = await _download_file(file_path)
    chunker = ChunkerService()
    return await chunker.process_file(file_bytes, filename)


async def _build_embeddings(chunks: list[str]) -> list[list[float]]:
    embeddings: list[list[float]] = []
    for index, chunk in enumerate(chunks):
        embeddings.append(await embed_text(chunk))
        if index % 10 == 0:
            logger.debug("Embedding progress", extra={"processed": index})
    return embeddings


async def _store_knowledge(
    *,
    pool: object,
    project_id: str,
    chunks: list[str],
    embeddings: list[list[float]],
) -> None:
    repo = KnowledgeRepository(pool)
    await repo.add_knowledge_batch(
        project_id,
        [
            {"content": chunk, "embedding": embedding}
            for chunk, embedding in zip(chunks, embeddings, strict=True)
        ],
    )


async def _success_response(
    *,
    chat_id: str,
    project_id: str,
    pool: object,
    chunks_count: int,
) -> UploadResult:
    await _clear_state(chat_id)
    return (
        f"Загружено {chunks_count} чанков.\nБаза знаний обновлена.",
        await _get_project_menu_keyboard(project_id, pool),
    )


async def _failure_response(
    *,
    chat_id: str,
    project_id: str,
    pool: object,
) -> UploadResult:
    await _clear_state(chat_id)
    return (
        "Ошибка при обработке файла. Попробуйте другой файл или проверьте формат.",
        await _get_project_menu_keyboard(project_id, pool),
    )


async def handle_knowledge_upload(
    chat_id: str,
    message: dict[str, object],
    pool: object,
) -> UploadResult:
    project_id = await _project_id_for_upload(chat_id)

    if not project_id:
        logger.error("Project ID missing in state", extra={"chat_id": chat_id})
        await _clear_state(chat_id)
        return _missing_project_response()

    document, error_response = await _validate_document(
        chat_id=chat_id, message=message
    )
    if error_response is not None:
        return error_response
    if document is None:
        logger.error(
            "Validated document payload missing after validation",
            extra={
                "chat_id": chat_id,
                "project_id": project_id,
                "policy": "safe_user_fallback",
            },
        )
        return await _failure_response(
            chat_id=chat_id,
            project_id=project_id,
            pool=pool,
        )
    file_id, filename = _document_metadata(document)

    logger.info(
        "Starting knowledge upload",
        extra={"project_id": project_id, "filename": filename},
    )

    try:
        chunks = await _chunk_document(file_id, filename)
        if not chunks:
            logger.warning("No chunks generated", extra={"filename": filename})
            return _no_chunks_response()

        embeddings = await _build_embeddings(chunks)
        await _store_knowledge(
            pool=pool,
            project_id=project_id,
            chunks=chunks,
            embeddings=embeddings,
        )

        logger.info(
            "Knowledge base updated",
            extra={"project_id": project_id, "chunks": len(chunks)},
        )
        return await _success_response(
            chat_id=chat_id,
            project_id=project_id,
            pool=pool,
            chunks_count=len(chunks),
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
        return await _failure_response(
            chat_id=chat_id,
            project_id=project_id,
            pool=pool,
        )
