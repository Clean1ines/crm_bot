from __future__ import annotations

from collections.abc import Mapping
from typing import cast

import asyncpg

from src.application.errors import EmbeddingProviderError, ValidationError
from src.application.ports.knowledge.failed_batch_retry import (
    KnowledgeFailedBatchRetryRepositoryPort,
)
from src.application.ports.knowledge_port import (
    KnowledgeDbPoolPort,
    ModelUsageRepositoryPort,
)
from src.application.services.knowledge_failed_batch_retry_service import (
    KnowledgeFailedBatchRetryService,
)
from src.domain.project_plane.knowledge_preprocessing import (
    MODE_FAQ,
    KnowledgePreprocessingValidationError,
)
from src.infrastructure.db.repositories.knowledge_repository import KnowledgeRepository
from src.infrastructure.db.repositories.model_usage_repository import (
    ModelUsageRepository,
)
from src.infrastructure.llm.knowledge_preprocessor import GroqKnowledgePreprocessor
from src.infrastructure.logging.logger import get_logger
from src.infrastructure.queue.job_exceptions import PermanentJobError, TransientJobError

logger = get_logger(__name__)


def make_model_usage_repository(
    pool: KnowledgeDbPoolPort,
) -> ModelUsageRepositoryPort:
    return cast(ModelUsageRepositoryPort, ModelUsageRepository(pool))


def make_knowledge_repository(
    pool: KnowledgeDbPoolPort,
) -> KnowledgeFailedBatchRetryRepositoryPort:
    return cast(KnowledgeFailedBatchRetryRepositoryPort, KnowledgeRepository(pool))


def _payload(job: Mapping[str, object]) -> Mapping[str, object]:
    payload = job.get("payload") or {}
    if not isinstance(payload, Mapping):
        raise PermanentJobError(
            "knowledge failed batch retry payload must be an object"
        )
    return payload


def _required_text(payload: Mapping[str, object], key: str) -> str:
    value = str(payload.get(key) or "").strip()
    if not value:
        raise PermanentJobError(f"knowledge failed batch retry job missing {key}")
    return value


async def handle_retry_knowledge_failed_batches(
    job: Mapping[str, object],
    *,
    db_pool: asyncpg.Pool,
) -> None:
    payload = _payload(job)
    project_id = _required_text(payload, "project_id")
    document_id = _required_text(payload, "document_id")
    preprocessing_mode = str(payload.get("preprocessing_mode") or "").strip().lower()
    if preprocessing_mode == MODE_FAQ:
        raise PermanentJobError(
            "Legacy knowledge failed-batches retry handler cannot process mode=faq. "
            "Use Retrieval Surface Compilation pipeline."
        )

    service = KnowledgeFailedBatchRetryService(db_pool)

    try:
        await service.retry_failed_batches(
            project_id=project_id,
            document_id=document_id,
            knowledge_repo_factory=make_knowledge_repository,
            model_usage_repo_factory=make_model_usage_repository,
            preprocessor_factory=GroqKnowledgePreprocessor,
            logger=logger,
        )
    except (KnowledgePreprocessingValidationError, ValidationError) as exc:
        raise PermanentJobError(str(exc)) from exc
    except EmbeddingProviderError as exc:
        if exc.retryable:
            raise TransientJobError(
                exc.detail,
                retry_after_seconds=getattr(exc, "retry_after_seconds", None),
            ) from exc
        raise PermanentJobError(exc.detail) from exc
