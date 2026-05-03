from __future__ import annotations

from typing import cast

from collections.abc import Mapping

import asyncpg

from src.application.errors import EmbeddingProviderError
from src.application.dto.knowledge_dto import KnowledgeUploadJobPayloadDto
from src.application.services.knowledge_ingestion_service import (
    KnowledgeIngestionService,
)
from src.infrastructure.db.repositories.knowledge_repository import KnowledgeRepository
from src.infrastructure.db.repositories.model_usage_repository import (
    ModelUsageRepository,
)
from src.infrastructure.llm.knowledge_preprocessor import GroqKnowledgePreprocessor
from src.infrastructure.logging.logger import get_logger
from src.infrastructure.queue.job_exceptions import PermanentJobError, TransientJobError
from src.application.ports.knowledge_port import (
    KnowledgeDbPoolPort,
    ModelUsageRepositoryPort,
)

logger = get_logger(__name__)
EXHAUSTED_KNOWLEDGE_UPLOAD_DETAIL = (
    "Knowledge upload failed after repeated temporary embedding provider errors"
)


def make_model_usage_repository(
    pool: KnowledgeDbPoolPort,
) -> ModelUsageRepositoryPort:
    return cast(ModelUsageRepositoryPort, ModelUsageRepository(pool))


async def handle_process_knowledge_upload(
    job: Mapping[str, object],
    *,
    db_pool: asyncpg.Pool,
) -> None:
    payload = job.get("payload") or {}
    if not isinstance(payload, Mapping):
        raise PermanentJobError("knowledge upload payload must be an object")

    try:
        dto = KnowledgeUploadJobPayloadDto.from_mapping(payload)
        mode = dto.normalized_preprocessing_mode()
    except ValueError as exc:
        raise PermanentJobError(str(exc)) from exc

    service = KnowledgeIngestionService(db_pool)
    try:
        await service.process_document(
            project_id=dto.project_id,
            document_id=dto.document_id,
            file_name=dto.file_name,
            chunks=dto.chunks,
            mode=mode,
            knowledge_repo_factory=KnowledgeRepository,
            model_usage_repo_factory=make_model_usage_repository,
            preprocessor_factory=GroqKnowledgePreprocessor,
            logger=logger,
        )
    except EmbeddingProviderError as exc:
        if exc.retryable:
            raise TransientJobError(
                exc.detail,
                retry_after_seconds=getattr(exc, "retry_after_seconds", None),
            ) from exc
        raise PermanentJobError(exc.detail) from exc


async def mark_process_knowledge_upload_exhausted(
    job: Mapping[str, object],
    *,
    db_pool: asyncpg.Pool,
) -> None:
    payload = job.get("payload") or {}
    if not isinstance(payload, Mapping):
        return

    try:
        dto = KnowledgeUploadJobPayloadDto.from_mapping(payload)
    except ValueError:
        return

    repo = KnowledgeRepository(db_pool)
    await repo.update_document_status(
        dto.document_id,
        "error",
        EXHAUSTED_KNOWLEDGE_UPLOAD_DETAIL,
    )
