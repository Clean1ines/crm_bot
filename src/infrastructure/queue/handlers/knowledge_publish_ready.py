from __future__ import annotations

from collections.abc import Mapping
from typing import cast

import asyncpg

from src.application.errors import EmbeddingProviderError, ValidationError
from src.application.ports.knowledge_port import KnowledgeDbPoolPort
from src.application.services.knowledge_ingestion_service import (
    KnowledgeIngestionRepositoryPort,
    KnowledgeIngestionService,
)
from src.domain.project_plane.knowledge_preprocessing import (
    MODE_FAQ,
    KnowledgePreprocessingValidationError,
)
from src.infrastructure.db.repositories.knowledge_repository import KnowledgeRepository
from src.infrastructure.logging.logger import get_logger
from src.infrastructure.queue.job_exceptions import PermanentJobError, TransientJobError

logger = get_logger(__name__)


def make_knowledge_repository(
    pool: KnowledgeDbPoolPort,
) -> KnowledgeIngestionRepositoryPort:
    return cast(KnowledgeIngestionRepositoryPort, KnowledgeRepository(pool))


def _payload(job: Mapping[str, object]) -> Mapping[str, object]:
    payload = job.get("payload") or {}
    if not isinstance(payload, Mapping):
        raise PermanentJobError("knowledge ready publish payload must be an object")
    return payload


def _required_text(payload: Mapping[str, object], key: str) -> str:
    value = str(payload.get(key) or "").strip()
    if not value:
        raise PermanentJobError(f"knowledge ready publish job missing {key}")
    return value


async def handle_publish_knowledge_ready_answers(
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
            "Legacy knowledge publish-ready handler cannot process mode=faq. "
            "Use Retrieval Surface Compilation pipeline."
        )

    service = KnowledgeIngestionService(db_pool)

    try:
        await service.publish_ready_answers(
            project_id=project_id,
            document_id=document_id,
            knowledge_repo_factory=make_knowledge_repository,
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
