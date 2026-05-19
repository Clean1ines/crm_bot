from collections.abc import Mapping
from typing import cast

import asyncpg

from src.application.errors import EmbeddingProviderError, ValidationError
from src.application.ports.knowledge_port import (
    KnowledgeDbPoolPort,
    KnowledgeRepositoryPort,
)
from src.application.services.knowledge_ingestion_service import (
    KnowledgeIngestionService,
)
from src.domain.project_plane.knowledge_preprocessing import (
    KnowledgePreprocessingValidationError,
)
from src.infrastructure.db.repositories.knowledge_repository import KnowledgeRepository
from src.infrastructure.llm.knowledge_preprocessor import GroqKnowledgePreprocessor
from src.infrastructure.logging.logger import get_logger
from src.infrastructure.queue.job_exceptions import PermanentJobError, TransientJobError

logger = get_logger(__name__)


def make_knowledge_repository(pool: KnowledgeDbPoolPort) -> KnowledgeRepositoryPort:
    return cast(KnowledgeRepositoryPort, KnowledgeRepository(pool))


async def handle_resume_knowledge_processing(
    job: Mapping[str, object], *, db_pool: asyncpg.Pool
) -> None:
    payload = job.get("payload") or {}
    if not isinstance(payload, Mapping):
        raise PermanentJobError("Job payload must be an object")

    project_id = str(payload.get("project_id") or "").strip()
    document_id = str(payload.get("document_id") or "").strip()
    if not project_id or not document_id:
        raise PermanentJobError("Missing project_id or document_id")

    service = KnowledgeIngestionService(db_pool)
    try:
        await service.resume_processing(
            project_id=project_id,
            document_id=document_id,
            knowledge_repo_factory=make_knowledge_repository,
            preprocessor_factory=GroqKnowledgePreprocessor,
            logger=logger,
        )
    except (ValidationError, KnowledgePreprocessingValidationError) as exc:
        raise PermanentJobError(str(exc)) from exc
    except EmbeddingProviderError as exc:
        if exc.retryable:
            raise TransientJobError(
                exc.detail,
                retry_after_seconds=getattr(exc, "retry_after_seconds", None),
            ) from exc
        raise PermanentJobError(exc.detail) from exc
