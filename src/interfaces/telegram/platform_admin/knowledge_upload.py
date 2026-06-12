"""
Platform admin bot handler for uploading knowledge base files.
"""

import aiohttp
import asyncpg
from dataclasses import dataclass
from datetime import datetime, timezone

from telegram import InlineKeyboardMarkup

from src.infrastructure.config.settings import settings
from src.contexts.knowledge_workbench.application.sagas.run_source_ingestion_first_phase import (
    RunSourceIngestionFirstPhaseCommand,
)
from src.contexts.knowledge_workbench.application.sagas.source_ingestion_admission import (
    SourceIngestionActor,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_format import (
    SourceFormat,
)
from src.infrastructure.db.repositories.user_repository import UserRepository
from src.interfaces.composition.knowledge_extraction_after_upload_composition import (
    make_knowledge_extraction_workflow_after_upload,
)
from src.interfaces.composition.knowledge_extraction_workflow_after_upload import (
    RunKnowledgeExtractionWorkflowAfterUploadCommand,
)
from src.interfaces.composition.project_repositories import build_project_repository
from src.infrastructure.logging.logger import get_logger
from src.domain.project_plane.knowledge_processing_modes import (
    KnowledgeProcessingModeValidationError,
    require_faq_workbench_mode,
)
from src.interfaces.telegram.platform_admin.handlers import _get_project_menu_keyboard
from src.interfaces.telegram.platform_admin.state import (
    clear_admin_state,
    get_admin_data,
)

logger = get_logger(__name__)


def _normalize_workbench_upload_mode(value: object) -> str:
    try:
        return require_faq_workbench_mode(value)
    except KnowledgeProcessingModeValidationError as exc:
        raise ValueError(
            "Only FAQ Workbench uploads are supported by the platform admin bot "
            "until legacy non-FAQ modes have first-class Workbench implementations."
        ) from exc


DocumentPayload = dict[str, object]
UploadResult = tuple[str, InlineKeyboardMarkup | None]


@dataclass(frozen=True, slots=True)
class TelegramKnowledgeUploadResult:
    document_id: str
    chunks: int
    preprocessing_mode: str
    preprocessing_status: str


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


async def _upload_context_for_upload(chat_id: str) -> tuple[str | None, str]:
    data = await get_admin_data(chat_id)
    project_id = data.get("project_id")
    try:
        preprocessing_mode = _normalize_workbench_upload_mode(
            data.get("preprocessing_mode")
        )
    except ValueError:
        preprocessing_mode = "faq"

    if project_id is None:
        return None, preprocessing_mode
    return str(project_id), preprocessing_mode


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


async def _download_document(file_id: str) -> bytes:
    file_path = await _get_file_path(file_id)
    return await _download_file(file_path)


def _source_format_from_upload_name(file_name: str) -> SourceFormat:
    normalized = file_name.strip().lower()
    suffix = ""
    if "." in normalized:
        suffix = "." + normalized.rsplit(".", 1)[-1]

    if suffix in {".md", ".markdown"}:
        return SourceFormat.MARKDOWN
    if suffix == ".pdf":
        return SourceFormat.PDF
    if suffix == ".html":
        return SourceFormat.HTML
    return SourceFormat.PLAIN_TEXT


def _decode_knowledge_upload_text(file_content: bytes) -> str:
    try:
        text = file_content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(
            "Knowledge upload must be UTF-8 text for source ingestion v1"
        ) from exc

    if not text.strip():
        raise ValueError("Knowledge upload text is empty")

    return text


async def _queue_knowledge_upload(
    *,
    pool: asyncpg.Pool,
    project_id: str,
    filename: str,
    file_content: bytes,
    preprocessing_mode: str,
):
    normalized_mode = _normalize_workbench_upload_mode(preprocessing_mode)
    raw_text = _decode_knowledge_upload_text(file_content)

    project_repo = build_project_repository(pool)
    user_repo = UserRepository(pool)
    workflow_runner = make_knowledge_extraction_workflow_after_upload(
        pool=pool,
        project_repo=project_repo,
        user_repo=user_repo,
    )

    result = await workflow_runner.execute(
        RunKnowledgeExtractionWorkflowAfterUploadCommand(
            source_ingestion_command=RunSourceIngestionFirstPhaseCommand(
                project_id=project_id,
                actor=SourceIngestionActor(
                    actor_user_id="telegram_platform_admin",
                    is_platform_admin=True,
                ),
                original_filename=filename,
                source_format=_source_format_from_upload_name(filename),
                content_bytes=bytes(file_content),
                raw_text=raw_text,
                occurred_at=datetime.now(timezone.utc),
            ),
            max_drain_commands=10,
        )
    )

    if not result.source_ingestion_completed:
        admission_status = result.source_ingestion_admission_status
        detail = admission_status.value if admission_status is not None else "unknown"
        raise ValueError(f"Source ingestion rejected: {detail}")

    if result.source_document_ref is None:
        raise ValueError("Source ingestion completed without source_document_ref")

    return TelegramKnowledgeUploadResult(
        document_id=result.source_document_ref,
        chunks=result.source_unit_count,
        preprocessing_mode=normalized_mode,
        preprocessing_status=(
            "workflow_blocked"
            if result.blocked_command_type is not None
            else "workflow_drained"
        ),
    )


async def _success_response(
    *,
    chat_id: str,
    project_id: str,
    pool: object,
    chunks_count: int,
) -> UploadResult:
    await clear_admin_state(chat_id)
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
    await clear_admin_state(chat_id)
    return (
        "Ошибка при обработке файла. Попробуйте другой файл или проверьте формат.",
        await _get_project_menu_keyboard(project_id, pool),
    )


async def handle_knowledge_upload(
    chat_id: str,
    message: dict[str, object],
    pool: asyncpg.Pool,
) -> UploadResult:
    project_id, preprocessing_mode = await _upload_context_for_upload(chat_id)

    if not project_id:
        logger.error("Project ID missing in state", extra={"chat_id": chat_id})
        await clear_admin_state(chat_id)
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
        extra={
            "project_id": project_id,
            "filename": filename,
            "preprocessing_mode": preprocessing_mode,
        },
    )

    try:
        file_content = await _download_document(file_id)
        result = await _queue_knowledge_upload(
            pool=pool,
            project_id=project_id,
            filename=filename,
            file_content=file_content,
            preprocessing_mode=preprocessing_mode,
        )
        if result.chunks <= 0:
            logger.warning("No chunks generated", extra={"filename": filename})
            return _no_chunks_response()

        logger.info(
            "Knowledge upload started via source-ingestion workflow",
            extra={
                "project_id": project_id,
                "document_id": result.document_id,
                "chunks": result.chunks,
                "preprocessing_mode": result.preprocessing_mode,
                "preprocessing_status": result.preprocessing_status,
            },
        )
        return await _success_response(
            chat_id=chat_id,
            project_id=project_id,
            pool=pool,
            chunks_count=result.chunks,
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
