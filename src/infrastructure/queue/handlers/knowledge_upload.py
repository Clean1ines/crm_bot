from __future__ import annotations

from collections.abc import Mapping

import asyncpg

from src.application.errors import EmbeddingProviderError
from src.application.dto.knowledge_dto import KnowledgeUploadJobPayloadDto
from src.application.services.knowledge_ingestion_service import (
    KnowledgeIngestionService,
)
from src.infrastructure.db.repositories.knowledge_repository import KnowledgeRepository
from src.infrastructure.llm.knowledge_preprocessor import GroqKnowledgePreprocessor
from src.infrastructure.logging.logger import get_logger
from src.infrastructure.queue.job_exceptions import PermanentJobError, TransientJobError

logger = get_logger(__name__)


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
            preprocessor_factory=GroqKnowledgePreprocessor,
            logger=logger,
        )
    except EmbeddingProviderError as exc:
        if exc.retryable:
            raise TransientJobError(exc.detail) from exc
        raise PermanentJobError(exc.detail) from exc
