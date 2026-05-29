from __future__ import annotations

from collections.abc import Mapping
from typing import cast

import asyncpg

from src.application.errors import EmbeddingProviderError, ValidationError
from src.application.ports.knowledge.retighten import (
    KnowledgeRetightenRepositoryPort,
)
from src.application.ports.knowledge_port import (
    KnowledgeDbPoolPort,
    ModelUsageRepositoryPort,
)
from src.application.services.knowledge_retighten_service import (
    KnowledgeRetightenService,
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


def _payload(job: Mapping[str, object]) -> Mapping[str, object]:
    payload = job.get("payload") or {}
    if not isinstance(payload, Mapping):
        raise PermanentJobError("knowledge retighten payload must be an object")
    return payload


def _required_text(payload: Mapping[str, object], key: str) -> str:
    value = str(payload.get(key) or "").strip()
    if not value:
        raise PermanentJobError(f"knowledge retighten job missing {key}")
    return value


def make_knowledge_repository(
    pool: KnowledgeDbPoolPort,
) -> KnowledgeRetightenRepositoryPort:
    return cast(KnowledgeRetightenRepositoryPort, KnowledgeRepository(pool))


async def handle_retighten_knowledge_document(
    job: Mapping[str, object],
    *,
    db_pool: asyncpg.Pool,
) -> None:
    payload = _payload(job)
    project_id = _required_text(payload, "project_id")
    document_id = _required_text(payload, "document_id")
    file_name = str(payload.get("file_name") or f"retighten:{document_id}")
    preprocessing_mode = str(payload.get("preprocessing_mode") or "").strip().lower()
    if preprocessing_mode == MODE_FAQ:
        raise PermanentJobError(
            "Legacy knowledge retighten handler cannot process mode=faq. "
            "Use Retrieval Surface Compilation pipeline."
        )

    service = KnowledgeRetightenService(db_pool)

    try:
        await service.retighten_processed_document(
            project_id=project_id,
            document_id=document_id,
            file_name=file_name,
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
