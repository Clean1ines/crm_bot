from __future__ import annotations

from collections.abc import Mapping
from typing import cast

import asyncpg

from src.application.dto.knowledge_dto import KnowledgeUploadJobPayloadDto
from src.application.errors import (
    EmbeddingProviderError,
    KnowledgeDocumentDeletedDuringProcessingError,
    ValidationError,
)
from src.application.ports.commercial_price import CommercialPriceKnowledgePort
from src.application.ports.knowledge.structured_ingestion import (
    KnowledgeStructuredIngestionRepositoryPort,
)
from src.application.ports.knowledge_port import (
    KnowledgeDbPoolPort,
    ModelUsageRepositoryPort,
)
from src.application.services.knowledge_ingestion_contracts import (
    KnowledgeIngestionRepositoryPort,
)
from src.application.services.knowledge_structured_ingestion_service import (
    KnowledgeStructuredIngestionService,
)
from src.application.services.knowledge_surface_ingestion_service import (
    KnowledgeFaqSurfaceIngestionService,
)
from src.domain.project_plane.knowledge_document_lifecycle import (
    KnowledgeDocumentLifecycleTrigger,
    TRIGGER_EXPLICIT_USER_RESUME,
    TRIGGER_NORMAL_UPLOAD,
    TRIGGER_QUOTA_RECOVERY,
    TRIGGER_STALE_JOB_RECOVERY,
    TRIGGER_WORKER_RECOVERY,
)
from src.domain.project_plane.knowledge_preprocessing import (
    MODE_FAQ,
    KnowledgePreprocessingMode,
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

FAQ_EXPLICIT_RESUME_SOURCE = "knowledge_document_resume"
AUTO_RECOVERY_UPLOAD_SOURCES: dict[str, KnowledgeDocumentLifecycleTrigger] = {
    "knowledge_upload_recovery": TRIGGER_WORKER_RECOVERY,
    "knowledge_document_auto_resume": TRIGGER_WORKER_RECOVERY,
    "knowledge_worker_recovery": TRIGGER_WORKER_RECOVERY,
    "worker_recovery": TRIGGER_WORKER_RECOVERY,
    "knowledge_provider_recovery": TRIGGER_WORKER_RECOVERY,
    "provider_recovery": TRIGGER_WORKER_RECOVERY,
    "knowledge_quota_recovery": TRIGGER_QUOTA_RECOVERY,
    "quota_recovery": TRIGGER_QUOTA_RECOVERY,
    "knowledge_stale_job_recovery": TRIGGER_STALE_JOB_RECOVERY,
    "stale_job_recovery": TRIGGER_STALE_JOB_RECOVERY,
}


def _knowledge_upload_lifecycle_trigger(
    source: str | None,
) -> KnowledgeDocumentLifecycleTrigger:
    if source == FAQ_EXPLICIT_RESUME_SOURCE:
        return TRIGGER_EXPLICIT_USER_RESUME
    if source is None:
        return TRIGGER_NORMAL_UPLOAD
    return AUTO_RECOVERY_UPLOAD_SOURCES.get(source, TRIGGER_NORMAL_UPLOAD)


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


def make_structured_knowledge_repository(
    pool: KnowledgeDbPoolPort,
) -> KnowledgeStructuredIngestionRepositoryPort:
    return cast(KnowledgeStructuredIngestionRepositoryPort, KnowledgeRepository(pool))


async def _mark_recoverable_llm_upload_failure(
    *,
    db_pool: asyncpg.Pool,
    dto: KnowledgeUploadJobPayloadDto,
    mode: KnowledgePreprocessingMode,
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
                lifecycle_trigger=_knowledge_upload_lifecycle_trigger(dto.source),
                resume_run_id=dto.resume_run_id,
            )
            return

        await KnowledgeStructuredIngestionService(db_pool).process_document(
            project_id=dto.project_id,
            document_id=dto.document_id,
            file_name=dto.file_name,
            chunks=dto.chunks,
            mode=mode,
            knowledge_repo_factory=make_structured_knowledge_repository,
            model_usage_repo_factory=make_model_usage_repository,
            preprocessor_factory=GroqKnowledgePreprocessor,
            logger=logger,
            commercial_price_repo_factory=make_commercial_price_repository,
            commercial_price_acquisition_service_factory=make_commercial_price_acquisition_service,
        )
    except KnowledgeDocumentDeletedDuringProcessingError as exc:
        logger.info(
            "Knowledge upload stopped because document was deleted or reset during processing",
            extra={
                "project_id": dto.project_id,
                "document_id": dto.document_id,
                "mode": mode,
                "error_type": type(exc).__name__,
            },
        )
        raise PermanentJobError(str(exc)) from exc
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
