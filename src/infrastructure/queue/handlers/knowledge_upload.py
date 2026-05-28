from __future__ import annotations

from collections.abc import Mapping
from typing import cast

import asyncpg

from src.application.dto.knowledge_dto import KnowledgeUploadJobPayloadDto
from src.application.errors import EmbeddingProviderError, ValidationError
from src.application.ports.commercial_price import CommercialPriceKnowledgePort
from src.application.ports.knowledge_port import (
    KnowledgeDbPoolPort,
    ModelUsageRepositoryPort,
)
from src.application.services.knowledge_ingestion_service import (
    KnowledgeIngestionRepositoryPort,
    KnowledgeIngestionService,
)
from src.application.services.knowledge_surface_ingestion_service import (
    KnowledgeFaqSurfaceIngestionService,
)
from src.domain.project_plane.knowledge_preprocessing import (
    MODE_FAQ,
    KnowledgePreprocessingValidationError,
)
from src.infrastructure.db.repositories.commercial_price_repository import (
    CommercialPriceRepository,
)
from src.infrastructure.db.repositories.knowledge_repository import KnowledgeRepository
from src.infrastructure.db.repositories.model_usage_repository import (
    ModelUsageRepository,
)
from src.infrastructure.llm.groq_router import GroqFallbackExhaustedError
from src.infrastructure.llm.knowledge_preprocessor import GroqKnowledgePreprocessor
from src.infrastructure.llm.knowledge_surface_quality_gated_compiler import (
    GroqQualityGatedKnowledgeSurfaceCompiler,
)
from src.infrastructure.logging.logger import get_logger
from src.infrastructure.queue.handlers.knowledge_upload_recovery import (
    NEEDS_RETRY_LATER_STATUS,
    recoverable_llm_error_type,
    recovery_decision_for_error_type,
    recovery_metrics,
)
from src.infrastructure.queue.job_exceptions import PermanentJobError, TransientJobError
from src.interfaces.composition.commercial_price_acquisition import (
    make_commercial_price_acquisition_service,
)

logger = get_logger(__name__)
EXHAUSTED_KNOWLEDGE_UPLOAD_DETAIL = (
    "Knowledge upload failed after repeated temporary embedding provider errors"
)


def make_model_usage_repository(
    pool: KnowledgeDbPoolPort,
) -> ModelUsageRepositoryPort:
    return cast(ModelUsageRepositoryPort, ModelUsageRepository(pool))


def make_commercial_price_repository(
    pool: KnowledgeDbPoolPort,
) -> CommercialPriceKnowledgePort:
    return cast(CommercialPriceKnowledgePort, CommercialPriceRepository(pool))


def make_knowledge_repository(
    pool: KnowledgeDbPoolPort,
) -> KnowledgeIngestionRepositoryPort:
    return cast(KnowledgeIngestionRepositoryPort, KnowledgeRepository(pool))


async def _mark_recoverable_llm_upload_failure(
    *,
    db_pool: asyncpg.Pool,
    dto: KnowledgeUploadJobPayloadDto,
    mode: str,
    error_type: str,
    error_message: str,
) -> None:
    repo = KnowledgeRepository(db_pool)
    decision = recovery_decision_for_error_type(error_type)
    await repo.update_document_preprocessing_status(
        dto.document_id,
        mode=mode,
        status=decision.document_status,
        error=error_message,
        metrics=recovery_metrics(decision),
    )
    await repo.update_document_status(
        dto.document_id,
        decision.document_status,
        error_message,
    )


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

    try:
        if mode == MODE_FAQ:
            await KnowledgeFaqSurfaceIngestionService(db_pool).process_document(
                project_id=dto.project_id,
                document_id=dto.document_id,
                file_name=dto.file_name,
                chunks=dto.chunks,
                knowledge_repo_factory=make_knowledge_repository,
                surface_compiler_factory=GroqQualityGatedKnowledgeSurfaceCompiler,
                logger=logger,
            )
            return

        await KnowledgeIngestionService(db_pool).process_document(
            project_id=dto.project_id,
            document_id=dto.document_id,
            file_name=dto.file_name,
            chunks=dto.chunks,
            mode=mode,
            knowledge_repo_factory=make_knowledge_repository,
            model_usage_repo_factory=make_model_usage_repository,
            preprocessor_factory=GroqKnowledgePreprocessor,
            logger=logger,
            commercial_price_repo_factory=make_commercial_price_repository,
            commercial_price_acquisition_service_factory=make_commercial_price_acquisition_service,
        )
    except (KnowledgePreprocessingValidationError, ValidationError) as exc:
        error_type = recoverable_llm_error_type(exc)
        if error_type is not None:
            error_message = str(exc)[:500] or type(exc).__name__
            await _mark_recoverable_llm_upload_failure(
                db_pool=db_pool,
                dto=dto,
                mode=mode,
                error_type=error_type,
                error_message=error_message,
            )
            logger.warning(
                "Knowledge upload paused after recoverable LLM failure",
                extra={
                    "project_id": dto.project_id,
                    "document_id": dto.document_id,
                    "mode": mode,
                    "error_type": error_type,
                },
            )
            return
        raise PermanentJobError(str(exc)) from exc
    except GroqFallbackExhaustedError as exc:
        error_message = str(exc)[:500] or type(exc).__name__
        await _mark_recoverable_llm_upload_failure(
            db_pool=db_pool,
            dto=dto,
            mode=mode,
            error_type=exc.failure_type.value,
            error_message=error_message,
        )
        logger.warning(
            "Knowledge upload paused after Groq fallback exhaustion",
            extra={
                "project_id": dto.project_id,
                "document_id": dto.document_id,
                "mode": mode,
                "error_type": exc.failure_type.value,
            },
        )
        return
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
        mode = dto.normalized_preprocessing_mode()
    except ValueError:
        return
    repo = KnowledgeRepository(db_pool)
    decision = recovery_decision_for_error_type("job_attempts_exhausted")
    await repo.update_document_preprocessing_status(
        dto.document_id,
        mode=mode,
        status=NEEDS_RETRY_LATER_STATUS,
        error=EXHAUSTED_KNOWLEDGE_UPLOAD_DETAIL,
        metrics=recovery_metrics(decision),
    )
    await repo.update_document_status(
        dto.document_id,
        NEEDS_RETRY_LATER_STATUS,
        EXHAUSTED_KNOWLEDGE_UPLOAD_DETAIL,
    )
