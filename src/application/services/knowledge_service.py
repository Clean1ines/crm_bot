from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from src.application.dto.knowledge_dto import (
    KnowledgeAnswerDraftDto,
    KnowledgeAnswerDraftsResponseDto,
    KnowledgeImportQualityReportDto,
    KnowledgePriceFactsMutationResultDto,
    KnowledgePriceFactsResponseDto,
    KnowledgeProcessingReportDto,
    KnowledgePreviewRequestDto,
    KnowledgePreviewResponseDto,
    KnowledgeSourceUnitDto,
    KnowledgeSourceUnitsResponseDto,
    KnowledgeUploadJobPayloadDto,
    KnowledgeUploadRequestDto,
    KnowledgeUploadResultDto,
)
from src.application.dto.model_usage_dto import ModelUsageSummaryDto
from src.application.ports.commercial_price import CommercialPriceKnowledgePort
from src.application.services.commercial_truth_review_service import (
    CommercialTruthReviewReport,
    CommercialTruthReviewService,
    commercial_source_descriptor_from_price_document,
)
from src.application.errors import (
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)
from src.application.ports.knowledge import (
    KnowledgeAnswerCandidatePort,
    KnowledgeCompilationTracePort,
    KnowledgeDocumentPort,
    KnowledgeRuntimeRetrievalPort,
    KnowledgeSourceMaterialPort,
)
from src.application.ports.knowledge_port import (
    JwtDecoderPort,
    KnowledgeChunkerFactoryPort,
    KnowledgeDbPoolPort,
    KnowledgePreprocessorFactoryPort,
    KnowledgeProjectAccessPort,
    KnowledgeQueuePort,
    ModelUsageRepositoryFactoryPort,
    PlatformUserAdminPort,
)
from src.application.ports.logger_port import LoggerPort
from src.application.services.knowledge_chunk_normalizer import (
    log_knowledge_chunk_audit,
    normalize_knowledge_chunks,
)
from src.application.services.knowledge_processing_report_builder import (
    build_knowledge_processing_report,
)
from src.domain.project_plane.json_types import JsonObject
from src.domain.project_plane.knowledge_compilation import AnswerCandidate
from src.domain.project_plane.knowledge_import_quality import (
    ImportQualitySourceUnit,
    build_document_import_quality_report,
)
from src.domain.project_plane.knowledge_views import (
    KnowledgeSearchResultView,
)
from src.domain.commercial.commercial_truth import CommercialTruthResolutionPolicy
from src.domain.project_plane.knowledge_preprocessing import (
    MODE_PLAIN,
    PREPROCESSING_STATUS_NOT_REQUESTED,
    PREPROCESSING_STATUS_PROCESSING,
    KnowledgePreprocessingValidationError,
)


class CommercialPriceKnowledgeFactoryPort(Protocol):
    def __call__(self, pool: KnowledgeDbPoolPort) -> CommercialPriceKnowledgePort: ...


class KnowledgeServiceRepositoryPort(
    KnowledgeDocumentPort,
    KnowledgeSourceMaterialPort,
    KnowledgeCompilationTracePort,
    KnowledgeAnswerCandidatePort,
    KnowledgeRuntimeRetrievalPort,
    Protocol,
):
    """Repository subset required by knowledge management workflows."""


class KnowledgeServiceRepositoryFactoryPort(Protocol):
    def __call__(self, pool: KnowledgeDbPoolPort) -> KnowledgeServiceRepositoryPort: ...


BEARER_PREFIX = "Bearer "
UPLOAD_FALLBACK_NAME = "upload"
KNOWLEDGE_PROCESSING_CANCELLED_MESSAGE = "Остановлено пользователем"


def _exact_answer_fingerprint(value: str) -> str:
    return " ".join(value.lower().replace("ё", "е").split())


def _dedupe_preview_results_by_exact_answer(
    results: Sequence[KnowledgeSearchResultView],
) -> list[KnowledgeSearchResultView]:
    deduped: list[KnowledgeSearchResultView] = []
    seen: set[str] = set()
    for result in results:
        fingerprint = _exact_answer_fingerprint(result.content)
        if fingerprint and fingerprint in seen:
            continue
        if fingerprint:
            seen.add(fingerprint)
        deduped.append(result)
    return deduped


def _candidate_source_indexes_for_report(candidate: object) -> tuple[int, ...]:
    metadata = getattr(candidate, "metadata", {})
    source_refs = getattr(candidate, "source_refs", ())
    indexes: list[int] = []

    if isinstance(metadata, Mapping):
        raw_indexes = metadata.get("source_chunk_indexes")
        if isinstance(raw_indexes, list | tuple):
            for raw_index in raw_indexes:
                parsed = _json_int_value(raw_index)
                if parsed is not None and parsed not in indexes:
                    indexes.append(parsed)

    if isinstance(source_refs, Sequence):
        for source_ref in source_refs:
            raw_index = getattr(source_ref, "source_index", None)
            parsed = _json_int_value(raw_index)
            if parsed is not None and parsed not in indexes:
                indexes.append(parsed)

    return tuple(indexes)


def _json_int_value(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


@dataclass(frozen=True)
class KnowledgeServiceConfig:
    jwt_algorithm: str = "HS256"
    model_usage_monthly_token_budget: int = 0
    voyage_free_monthly_tokens: int = 0
    model_usage_counter_enabled: bool = True


def _clean_price_fact_ids(fact_ids: Sequence[str]) -> tuple[str, ...]:
    cleaned = tuple(fact_id.strip() for fact_id in fact_ids if fact_id.strip())
    if not cleaned:
        raise ValidationError("At least one price fact id is required")
    return cleaned


def _clean_price_rejection_reason(reason: str) -> str:
    cleaned = reason.strip()
    if not cleaned:
        raise ValidationError("Price fact rejection reason is required")
    return cleaned


class KnowledgeService:
    def __init__(
        self,
        project_repo: KnowledgeProjectAccessPort,
        user_repo: PlatformUserAdminPort,
        pool: KnowledgeDbPoolPort,
        jwt_secret: str,
        jwt_module: JwtDecoderPort,
        service_config: KnowledgeServiceConfig | None = None,
    ) -> None:
        self.project_repo = project_repo
        self.user_repo = user_repo
        self.pool = pool
        self.jwt_secret = jwt_secret
        self.jwt = jwt_module
        self.config = service_config or KnowledgeServiceConfig()

    async def require_access(self, project_id: str, authorization: str | None) -> str:
        user_id = self._user_id_from_authorization(authorization)
        if await self._has_project_admin_access(project_id, user_id):
            return user_id

        raise ForbiddenError("Insufficient permissions")

    async def _uploaded_by_user_id(
        self,
        project_id: str,
        authorization: str | None,
        *,
        uploaded_by_user_id: str | None,
        trusted_upload: bool,
    ) -> str | None:
        if trusted_upload:
            if uploaded_by_user_id is None:
                return None
            uploaded_by = uploaded_by_user_id.strip()
            return uploaded_by or None

        if uploaded_by_user_id is not None:
            uploaded_by = uploaded_by_user_id.strip()
            if not uploaded_by:
                raise UnauthorizedError("Invalid uploader identity")
            return uploaded_by

        return await self.require_access(project_id, authorization)

    def _user_id_from_authorization(self, authorization: str | None) -> str:
        token = _extract_bearer_token(authorization)
        return self._user_id_from_token(token)

    def _user_id_from_token(self, token: str) -> str:
        try:
            payload = self.jwt.decode(token, self.jwt_secret, algorithms=["HS256"])
            return _subject_from_payload(payload)
        except self.jwt.ExpiredSignatureError:
            raise UnauthorizedError("Token expired") from None
        except (self.jwt.InvalidTokenError, ValueError):
            raise UnauthorizedError("Invalid token") from None

    async def _has_project_admin_access(self, project_id: str, user_id: str) -> bool:
        if await self.user_repo.is_platform_admin(user_id):
            return True

        has_role = await self.project_repo.user_has_project_role(
            project_id,
            user_id,
            ["owner", "admin"],
        )
        return has_role is True or await self._owns_project(project_id, user_id)

    async def _owns_project(self, project_id: str, user_id: str) -> bool:
        project_view = await self.project_repo.get_project_view(project_id)
        return bool(project_view and str(project_view.user_id) == user_id)

    async def upload(
        self,
        project_id: str,
        file_name: str | None,
        file_content: bytes | bytearray,
        authorization: str | None,
        *,
        chunker_factory: KnowledgeChunkerFactoryPort,
        knowledge_repo_factory: KnowledgeServiceRepositoryFactoryPort,
        logger: LoggerPort,
        queue_repo: KnowledgeQueuePort,
        knowledge_upload_task_type: str,
        upload_request: KnowledgeUploadRequestDto | None = None,
        preprocessor_factory: KnowledgePreprocessorFactoryPort | None = None,
        uploaded_by_user_id: str | None = None,
        trusted_upload: bool = False,
    ) -> KnowledgeUploadResultDto:
        try:
            mode = (
                upload_request or KnowledgeUploadRequestDto()
            ).normalized_preprocessing_mode()
        except KnowledgePreprocessingValidationError as exc:
            raise ValidationError(str(exc)) from None

        if mode != MODE_PLAIN and preprocessor_factory is None:
            raise ValidationError(
                "Knowledge preprocessing adapter is required for non-plain upload modes"
            )

        uploaded_by = await self._uploaded_by_user_id(
            project_id,
            authorization,
            uploaded_by_user_id=uploaded_by_user_id,
            trusted_upload=trusted_upload,
        )
        normalized_file_name = file_name or UPLOAD_FALLBACK_NAME
        logger.info(
            f"Knowledge upload requested for project {project_id}, file: {normalized_file_name}"
        )

        await self._ensure_project_exists(project_id, logger)

        chunks = await self._extract_chunks(
            file_content,
            normalized_file_name,
            chunker_factory=chunker_factory,
            logger=logger,
        )
        log_knowledge_chunk_audit(logger, chunks, context="upload_normalized")
        if not chunks:
            logger.warning("No text extracted from file")
            return KnowledgeUploadResultDto.create(
                message="No text extracted", chunks=0
            )

        repo = knowledge_repo_factory(self.pool)
        document_id = await repo.create_document(
            project_id=project_id,
            file_name=normalized_file_name,
            file_size=len(file_content),
            uploaded_by=uploaded_by,
        )

        await repo.update_document_status(document_id, "processing")

        if mode != MODE_PLAIN:
            await repo.update_document_preprocessing_status(
                document_id,
                mode=mode,
                status=PREPROCESSING_STATUS_PROCESSING,
            )

        job_payload = KnowledgeUploadJobPayloadDto(
            project_id=project_id,
            document_id=document_id,
            file_name=normalized_file_name,
            preprocessing_mode=mode,
            chunks=chunks,
        )

        try:
            await queue_repo.enqueue(
                knowledge_upload_task_type,
                payload=job_payload.to_dict(),
            )
        except Exception as exc:
            logger.exception(
                "Knowledge upload enqueue failed",
                extra={"project_id": project_id, "document_id": document_id},
            )
            await repo.update_document_status(document_id, "error", str(exc))
            raise

        preprocessing_status = (
            PREPROCESSING_STATUS_NOT_REQUESTED
            if mode == MODE_PLAIN
            else PREPROCESSING_STATUS_PROCESSING
        )
        logger.info("Knowledge upload queued", extra={"document_id": document_id})
        return KnowledgeUploadResultDto.create(
            message=f"Queued {len(chunks)} chunks for processing",
            chunks=len(chunks),
            document_id=document_id,
            preprocessing_mode=mode,
            preprocessing_status=preprocessing_status,
            structured_entries=0,
        )

    async def answer_drafts(
        self,
        project_id: str,
        document_id: str,
        authorization: str | None,
        *,
        knowledge_repo_factory: KnowledgeServiceRepositoryFactoryPort,
        logger: LoggerPort,
        limit: int = 20,
    ) -> KnowledgeAnswerDraftsResponseDto:
        await self.require_access(project_id, authorization)
        await self._ensure_project_exists(project_id, logger)

        repo = knowledge_repo_factory(self.pool)
        document = await repo.get_document(document_id)
        if document is None or document.project_id != project_id:
            raise NotFoundError("Knowledge document not found")

        raw_candidates = await repo.list_document_raw_answer_candidates(
            project_id=project_id,
            document_id=document_id,
        )
        normalized_limit = max(1, min(int(limit), 1000))
        drafts = tuple(
            KnowledgeAnswerDraftDto.from_candidate(candidate)
            for candidate in raw_candidates[:normalized_limit]
        )

        logger.info(
            "Knowledge answer drafts listed",
            extra={
                "project_id": project_id,
                "document_id": document_id,
                "draft_count": len(drafts),
                "total_count": len(raw_candidates),
            },
        )
        return KnowledgeAnswerDraftsResponseDto(
            document_id=document_id,
            drafts=drafts,
            total_count=len(raw_candidates),
        )

    async def source_units(
        self,
        project_id: str,
        document_id: str,
        authorization: str | None,
        *,
        knowledge_repo_factory: KnowledgeServiceRepositoryFactoryPort,
        logger: LoggerPort,
        limit: int = 1000,
    ) -> KnowledgeSourceUnitsResponseDto:
        await self.require_access(project_id, authorization)
        await self._ensure_project_exists(project_id, logger)

        repo = knowledge_repo_factory(self.pool)
        document = await repo.get_document(document_id)
        if document is None or document.project_id != project_id:
            raise NotFoundError("Knowledge document not found")

        source_chunks = await repo.list_document_source_chunks(
            project_id=project_id,
            document_id=document_id,
        )
        raw_candidates = await repo.list_document_raw_answer_candidates(
            project_id=project_id,
            document_id=document_id,
        )

        candidates_by_source_index: dict[int, list[AnswerCandidate]] = {}
        for candidate in raw_candidates:
            for source_index in _candidate_source_indexes_for_report(candidate):
                candidates_by_source_index.setdefault(source_index, []).append(
                    candidate
                )

        normalized_limit = max(1, min(int(limit), 1000))
        units = tuple(
            KnowledgeSourceUnitDto.from_source_chunk(
                source_chunk,
                related_candidates=tuple(
                    candidate
                    for candidate in candidates_by_source_index.get(
                        source_chunk.source_index,
                        [],
                    )
                ),
            )
            for source_chunk in source_chunks[:normalized_limit]
        )

        logger.info(
            "Knowledge source units listed",
            extra={
                "project_id": project_id,
                "document_id": document_id,
                "source_unit_count": len(units),
                "total_count": len(source_chunks),
            },
        )
        return KnowledgeSourceUnitsResponseDto(
            document_id=document_id,
            source_units=units,
            total_count=len(source_chunks),
        )

    async def import_quality_report(
        self,
        project_id: str,
        document_id: str,
        authorization: str | None,
        *,
        knowledge_repo_factory: KnowledgeServiceRepositoryFactoryPort,
        logger: LoggerPort,
    ) -> KnowledgeImportQualityReportDto:
        await self.require_access(project_id, authorization)
        await self._ensure_project_exists(project_id, logger)

        repo = knowledge_repo_factory(self.pool)
        document = await repo.get_document(document_id)
        if document is None or document.project_id != project_id:
            raise NotFoundError("Knowledge document not found")

        source_chunks = await repo.list_document_source_chunks(
            project_id=project_id,
            document_id=document_id,
        )
        report = build_document_import_quality_report(
            document_id=document_id,
            file_name=document.file_name,
            document_status=document.status,
            preprocessing_status=document.preprocessing_status,
            preprocessing_metrics=document.preprocessing_metrics,
            source_units=tuple(
                ImportQualitySourceUnit(
                    content=source_chunk.content,
                    section_title=source_chunk.section_title,
                    metadata=source_chunk.metadata,
                )
                for source_chunk in source_chunks
            ),
        )

        logger.info(
            "Knowledge import quality report built",
            extra={
                "project_id": project_id,
                "document_id": document_id,
                "status": report.status,
                "source_units_count": report.source_units_count,
                "warning_count": len(report.warnings),
            },
        )
        return KnowledgeImportQualityReportDto.from_domain(report)

    async def processing_report(
        self,
        project_id: str,
        document_id: str,
        authorization: str | None,
        *,
        knowledge_repo_factory: KnowledgeServiceRepositoryFactoryPort,
        logger: LoggerPort,
    ) -> KnowledgeProcessingReportDto:
        await self.require_access(project_id, authorization)
        await self._ensure_project_exists(project_id, logger)

        repo = knowledge_repo_factory(self.pool)
        document = await repo.get_document(document_id)
        if document is None or document.project_id != project_id:
            raise NotFoundError("Knowledge document not found")

        batches = await repo.list_document_compiler_batches(
            project_id=project_id,
            document_id=document_id,
        )
        candidate_summary = await repo.get_document_answer_candidate_summary(
            project_id=project_id,
            document_id=document_id,
        )

        return build_knowledge_processing_report(
            document_id=document_id,
            document=document,
            batches=batches,
            candidate_summary=candidate_summary,
        )

    async def price_facts(
        self,
        project_id: str,
        document_id: str,
        authorization: str | None,
        *,
        commercial_price_repo_factory: CommercialPriceKnowledgeFactoryPort,
        logger: LoggerPort,
    ) -> KnowledgePriceFactsResponseDto:
        await self.require_access(project_id, authorization)
        await self._ensure_project_exists(project_id, logger)

        repo = commercial_price_repo_factory(self.pool)
        price_document = await repo.get_price_document_by_knowledge_document(
            project_id=project_id,
            knowledge_document_id=document_id,
        )
        if price_document is None:
            return KnowledgePriceFactsResponseDto.empty(
                knowledge_document_id=document_id,
            )

        facts = await repo.list_price_facts_for_document(
            project_id=project_id,
            price_document_id=price_document.id,
            include_non_runtime=True,
        )
        return KnowledgePriceFactsResponseDto.from_facts(
            knowledge_document_id=document_id,
            price_document_id=price_document.id,
            facts=facts,
        )

    async def publish_price_facts(
        self,
        project_id: str,
        document_id: str,
        fact_ids: Sequence[str],
        authorization: str | None,
        *,
        commercial_price_repo_factory: CommercialPriceKnowledgeFactoryPort,
        logger: LoggerPort,
    ) -> KnowledgePriceFactsMutationResultDto:
        await self.require_access(project_id, authorization)
        await self._ensure_project_exists(project_id, logger)

        cleaned_fact_ids = _clean_price_fact_ids(fact_ids)
        repo = commercial_price_repo_factory(self.pool)
        price_document = await repo.get_price_document_by_knowledge_document(
            project_id=project_id,
            knowledge_document_id=document_id,
        )
        if price_document is None:
            raise NotFoundError(
                "Price document was not found for this knowledge document"
            )

        affected_count = await repo.publish_price_facts(
            project_id=project_id,
            price_document_id=price_document.id,
            fact_ids=cleaned_fact_ids,
        )
        facts = await repo.list_price_facts_for_document(
            project_id=project_id,
            price_document_id=price_document.id,
            include_non_runtime=True,
        )
        return KnowledgePriceFactsMutationResultDto.from_facts(
            knowledge_document_id=document_id,
            price_document_id=price_document.id,
            affected_count=affected_count,
            facts=facts,
        )

    async def reject_price_facts(
        self,
        project_id: str,
        document_id: str,
        fact_ids: Sequence[str],
        reason: str,
        authorization: str | None,
        *,
        commercial_price_repo_factory: CommercialPriceKnowledgeFactoryPort,
        logger: LoggerPort,
    ) -> KnowledgePriceFactsMutationResultDto:
        await self.require_access(project_id, authorization)
        await self._ensure_project_exists(project_id, logger)

        cleaned_fact_ids = _clean_price_fact_ids(fact_ids)
        cleaned_reason = _clean_price_rejection_reason(reason)
        repo = commercial_price_repo_factory(self.pool)
        price_document = await repo.get_price_document_by_knowledge_document(
            project_id=project_id,
            knowledge_document_id=document_id,
        )
        if price_document is None:
            raise NotFoundError(
                "Price document was not found for this knowledge document"
            )

        affected_count = await repo.reject_price_facts(
            project_id=project_id,
            price_document_id=price_document.id,
            fact_ids=cleaned_fact_ids,
            reason=cleaned_reason,
        )
        facts = await repo.list_price_facts_for_document(
            project_id=project_id,
            price_document_id=price_document.id,
            include_non_runtime=True,
        )
        return KnowledgePriceFactsMutationResultDto.from_facts(
            knowledge_document_id=document_id,
            price_document_id=price_document.id,
            affected_count=affected_count,
            facts=facts,
        )

    async def commercial_truth_review(
        self,
        project_id: str,
        document_id: str,
        authorization: str | None,
        *,
        commercial_price_repo_factory: CommercialPriceKnowledgeFactoryPort,
        knowledge_repo_factory: KnowledgeServiceRepositoryFactoryPort,
        logger: LoggerPort,
        policy: CommercialTruthResolutionPolicy = (
            CommercialTruthResolutionPolicy.MANUAL_REVIEW
        ),
    ) -> CommercialTruthReviewReport:
        await self.require_access(project_id, authorization)
        await self._ensure_project_exists(project_id, logger)

        price_repo = commercial_price_repo_factory(self.pool)
        price_document = await price_repo.get_price_document_by_knowledge_document(
            project_id=project_id,
            knowledge_document_id=document_id,
        )
        if price_document is None:
            return CommercialTruthReviewService().review_price_facts(
                facts=(),
                sources_by_price_document_id={},
                policy=policy,
            )

        knowledge_repo = knowledge_repo_factory(self.pool)
        knowledge_document = await knowledge_repo.get_document(document_id)
        if (
            knowledge_document is not None
            and knowledge_document.project_id != project_id
        ):
            knowledge_document = None

        facts = await price_repo.list_price_facts_for_document(
            project_id=project_id,
            price_document_id=price_document.id,
            include_non_runtime=True,
        )
        return CommercialTruthReviewService().review_price_facts(
            facts=facts,
            sources_by_price_document_id={
                price_document.id: commercial_source_descriptor_from_price_document(
                    price_document,
                    knowledge_document=knowledge_document,
                )
            },
            policy=policy,
        )

    async def cancel_document_processing(
        self,
        project_id: str,
        document_id: str,
        authorization: str | None,
        *,
        knowledge_repo_factory: KnowledgeServiceRepositoryFactoryPort,
        logger: LoggerPort,
    ) -> None:
        await self.require_access(project_id, authorization)
        await self._ensure_project_exists(project_id, logger)

        repo = knowledge_repo_factory(self.pool)
        cancelled = await repo.cancel_document_processing(
            project_id=project_id,
            document_id=document_id,
            reason=KNOWLEDGE_PROCESSING_CANCELLED_MESSAGE,
        )
        if not cancelled:
            raise NotFoundError("Knowledge document not found")

        logger.info(
            "Knowledge document processing cancelled",
            extra={"project_id": project_id, "document_id": document_id},
        )

    async def publish_document_ready_answers(
        self,
        project_id: str,
        document_id: str,
        authorization: str | None,
        *,
        queue_repo: KnowledgeQueuePort,
        publish_ready_task_type: str,
        logger: LoggerPort,
    ) -> JsonObject:
        user_id = await self.require_access(project_id, authorization)
        await self._ensure_project_exists(project_id, logger)

        job_id = await queue_repo.enqueue(
            publish_ready_task_type,
            payload={
                "project_id": project_id,
                "document_id": document_id,
                "requested_by": user_id,
                "source": "knowledge_ready_answer_publish",
            },
            max_attempts=3,
        )

        logger.info(
            "Knowledge ready answer publish queued",
            extra={
                "project_id": project_id,
                "document_id": document_id,
                "job_id": job_id,
            },
        )
        return {
            "status": "queued",
            "job_id": job_id,
            "document_id": document_id,
        }

    async def retry_document_failed_batches(
        self,
        project_id: str,
        document_id: str,
        authorization: str | None,
        *,
        queue_repo: KnowledgeQueuePort,
        retry_failed_batches_task_type: str,
        logger: LoggerPort,
    ) -> JsonObject:
        user_id = await self.require_access(project_id, authorization)
        await self._ensure_project_exists(project_id, logger)

        job_id = await queue_repo.enqueue(
            retry_failed_batches_task_type,
            payload={
                "project_id": project_id,
                "document_id": document_id,
                "requested_by": user_id,
                "source": "knowledge_failed_batch_retry",
            },
            max_attempts=3,
        )

        logger.info(
            "Knowledge failed batch retry queued",
            extra={
                "project_id": project_id,
                "document_id": document_id,
                "job_id": job_id,
            },
        )
        return {
            "status": "queued",
            "job_id": job_id,
            "document_id": document_id,
        }

    async def retighten_document_answer_resolution(
        self,
        project_id: str,
        document_id: str,
        authorization: str | None,
        *,
        queue_repo: KnowledgeQueuePort,
        retighten_task_type: str,
        logger: LoggerPort,
    ) -> JsonObject:
        user_id = await self.require_access(project_id, authorization)
        await self._ensure_project_exists(project_id, logger)

        job_id = await queue_repo.enqueue(
            retighten_task_type,
            payload={
                "project_id": project_id,
                "document_id": document_id,
                "requested_by": user_id,
                "source": "knowledge_document_retighten",
            },
            max_attempts=3,
        )

        logger.info(
            "Knowledge answer resolution retighten queued",
            extra={
                "project_id": project_id,
                "document_id": document_id,
                "job_id": job_id,
            },
        )
        return {
            "status": "queued",
            "job_id": job_id,
            "document_id": document_id,
        }

    async def preview_query(
        self,
        project_id: str,
        request: KnowledgePreviewRequestDto,
        authorization: str | None,
        *,
        knowledge_repo_factory: KnowledgeServiceRepositoryFactoryPort,
        logger: LoggerPort,
    ) -> KnowledgePreviewResponseDto:
        await self.require_access(project_id, authorization)
        await self._ensure_project_exists(project_id, logger)

        query = request.normalized_question()
        if not query:
            return KnowledgePreviewResponseDto.empty(query=query)

        repo = knowledge_repo_factory(self.pool)
        results = _dedupe_preview_results_by_exact_answer(
            await repo.preview_search(
                project_id=project_id,
                query=query,
                limit=max(request.normalized_limit() * 2, request.normalized_limit()),
            )
        )[: request.normalized_limit()]

        logger.info(
            "Knowledge preview search completed",
            extra={"project_id": project_id, "result_count": len(results)},
        )
        return KnowledgePreviewResponseDto.from_results(query=query, results=results)

    async def clear_project_knowledge(
        self,
        project_id: str,
        authorization: str | None,
        *,
        knowledge_repo_factory: KnowledgeServiceRepositoryFactoryPort,
        logger: LoggerPort,
    ) -> None:
        await self.require_access(project_id, authorization)
        await self._ensure_project_exists(project_id, logger)

        repo = knowledge_repo_factory(self.pool)
        await repo.clear_project_knowledge(project_id)
        logger.info(
            "Knowledge base cleared",
            extra={"project_id": project_id},
        )

    async def usage(
        self,
        project_id: str,
        authorization: str | None,
        *,
        model_usage_repo_factory: ModelUsageRepositoryFactoryPort,
    ) -> ModelUsageSummaryDto:
        await self.require_access(project_id, authorization)
        if not await self.project_repo.project_exists(project_id):
            raise NotFoundError("Project not found")

        monthly_budget_tokens = max(
            self.config.model_usage_monthly_token_budget,
            self.config.voyage_free_monthly_tokens,
        )
        if not self.config.model_usage_counter_enabled:
            return ModelUsageSummaryDto.disabled(
                monthly_budget_tokens=monthly_budget_tokens
            )

        now = datetime.now(UTC)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if month_start.month == 12:
            month_end = month_start.replace(year=month_start.year + 1, month=1)
        else:
            month_end = month_start.replace(month=month_start.month + 1)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        repo = model_usage_repo_factory(self.pool)
        summary = await repo.get_project_usage_summary(
            project_id=project_id,
            month_start_utc=month_start,
            month_end_utc=month_end,
            today_start_utc=today_start,
            monthly_budget_tokens=monthly_budget_tokens,
        )
        return ModelUsageSummaryDto.from_view(summary, counter_enabled=True)

    async def _ensure_project_exists(self, project_id: str, logger: LoggerPort) -> None:
        if await self.project_repo.project_exists(project_id):
            return

        logger.warning(f"Project {project_id} not found")
        raise NotFoundError("Project not found")

    async def _extract_chunks(
        self,
        file_content: bytes | bytearray,
        file_name: str,
        *,
        chunker_factory: KnowledgeChunkerFactoryPort,
        logger: LoggerPort,
    ) -> list[JsonObject]:
        chunker = chunker_factory()
        try:
            raw_chunks = await chunker.process_file(file_content, file_name)
        except ValueError as exc:
            logger.error(f"Chunking failed: {exc}")
            raise ValidationError(str(exc)) from None

        return normalize_knowledge_chunks(raw_chunks)


def _extract_bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise UnauthorizedError("Authorization header required")

    if not authorization.startswith(BEARER_PREFIX):
        raise UnauthorizedError("Invalid token format. Use 'Bearer <token>'")

    return authorization[len(BEARER_PREFIX) :]


def _subject_from_payload(payload: object) -> str:
    if not isinstance(payload, Mapping):
        raise ValueError("Invalid token payload")

    user_id = str(payload.get("sub") or "")
    if not user_id:
        raise ValueError("Missing subject claim")

    return user_id


_CHUNK_AUDIT_FIELDS: tuple[str, ...] = (
    "content",
    "entry_kind",
    "title",
    "source_excerpt",
    "questions",
    "synonyms",
    "tags",
    "embedding_text",
)
