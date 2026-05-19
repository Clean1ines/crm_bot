from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from src.application.dto.knowledge_dto import (
    KnowledgeAnswerDraftDto,
    KnowledgeAnswerDraftsResponseDto,
    KnowledgeProcessingActionDto,
    KnowledgeProcessingReportDto,
    KnowledgeProcessingStepDto,
    KnowledgePreviewRequestDto,
    KnowledgePreviewResponseDto,
    KnowledgeSourceUnitDto,
    KnowledgeSourceUnitsResponseDto,
    KnowledgeUploadJobPayloadDto,
    KnowledgeUploadRequestDto,
    KnowledgeUploadResultDto,
)
from src.application.dto.model_usage_dto import ModelUsageSummaryDto
from src.application.errors import (
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)
from src.application.ports.knowledge_port import (
    JwtDecoderPort,
    KnowledgeChunkerFactoryPort,
    KnowledgeDbPoolPort,
    ModelUsageRepositoryFactoryPort,
    KnowledgePreprocessorFactoryPort,
    KnowledgeProjectAccessPort,
    KnowledgeQueuePort,
    KnowledgeRepositoryFactoryPort,
    PlatformUserAdminPort,
)
from src.application.ports.logger_port import LoggerPort
from src.domain.project_plane.json_types import JsonObject, json_value_from_unknown
from src.domain.project_plane.knowledge_compilation import AnswerCandidate
from src.domain.project_plane.knowledge_views import (
    KnowledgeCompilerBatchView,
    KnowledgeSearchResultView,
)
from src.domain.project_plane.knowledge_preprocessing import (
    MODE_PLAIN,
    PREPROCESSING_STATUS_NOT_REQUESTED,
    PREPROCESSING_STATUS_PROCESSING,
    KnowledgePreprocessingValidationError,
)


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


def _answer_resolution_metrics(metrics: JsonObject) -> JsonObject:
    value = metrics.get("answer_resolution")
    return dict(value) if isinstance(value, Mapping) else {}


def _json_int_metric(metrics: JsonObject, key: str) -> int:
    value = metrics.get(key)
    if isinstance(value, bool) or value is None:
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return 0


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


def _answer_resolution_report_status(
    metrics: JsonObject, *, is_processing: bool
) -> str:
    status = str(metrics.get("status") or "")
    if status == "failed_fallback_published":
        return "failed"
    if status in {"processing", "completed", "failed"}:
        return status
    if is_processing:
        return "waiting"
    return "completed" if metrics else "pending"


def _batch_status_count(
    batches: Sequence[KnowledgeCompilerBatchView], status: str
) -> int:
    return sum(1 for batch in batches if batch.status == status)


def _knowledge_processing_title(
    *, document_status: str, preprocessing_status: str
) -> str:
    if preprocessing_status == "completed" or document_status == "processed":
        return "Готово: база знаний обновлена"
    if preprocessing_status == "failed" or document_status == "error":
        return "Обработка остановилась, но прогресс сохранён"
    if preprocessing_status == "cancelled" or document_status == "cancelled":
        return "Обработка остановлена"
    if preprocessing_status == "processing" or document_status in {
        "processing",
        "pending",
    }:
        return "Ищем ответы в документе"
    return "Документ подготовлен"


def _knowledge_processing_message(
    *,
    batch_total: int,
    batch_completed: int,
    batch_failed: int,
    raw_answer_count: int,
    published_answer_count: int,
) -> str:
    if batch_failed > 0 and published_answer_count > 0:
        return (
            f"Опубликовано ответов: {published_answer_count}. "
            f"Обработано {batch_completed} из {batch_total} частей. "
            f"Черновиков сохранено: {raw_answer_count}. "
            "Проблемные части можно повторить позже."
        )
    if batch_failed > 0:
        return (
            f"Обработано {batch_completed} из {batch_total} частей. "
            f"Найдено черновиков: {raw_answer_count}. "
            "Проблемные части можно повторить без потери уже сохранённого прогресса."
        )
    if batch_total > 0 and batch_completed < batch_total:
        return (
            f"Обработано {batch_completed} из {batch_total} частей. "
            f"Найдено черновиков: {raw_answer_count}. Черновики сохраняются после каждого шага."
        )
    if published_answer_count > 0:
        return f"Опубликовано ответов: {published_answer_count}. Черновики можно проверить или удалить позже."
    if raw_answer_count > 0:
        return f"Найдено черновиков: {raw_answer_count}. Их можно проверить и опубликовать."
    return "Документ ожидает обработки или пока не дал пригодных ответов."


def _knowledge_processing_actions(
    *,
    batch_failed: int,
    raw_answer_count: int,
    published_answer_count: int,
    is_processing: bool,
    answer_resolution_ready: bool,
    current_stage: str,
) -> tuple[KnowledgeProcessingActionDto, ...]:
    actions: list[KnowledgeProcessingActionDto] = []
    if is_processing:
        actions.append(
            KnowledgeProcessingActionDto(
                id="cancel",
                label="Остановить обработку",
                kind="destructive",
            )
        )
    if batch_failed > 0:
        actions.append(
            KnowledgeProcessingActionDto(
                id="retry_failed_batches",
                label="Повторить проблемные части",
                kind="primary",
                enabled=not is_processing,
            )
        )
    if raw_answer_count > published_answer_count:
        actions.append(
            KnowledgeProcessingActionDto(
                id="publish_ready",
                label=(
                    "Опубликовать черновики без уплотнения"
                    if current_stage == "answer_resolution_pending"
                    else "Опубликовать готовые ответы"
                ),
                kind="primary",
                enabled=not is_processing,
            )
        )
    if published_answer_count > 0:
        actions.append(
            KnowledgeProcessingActionDto(
                id="review_published",
                label="Проверить опубликованные ответы",
                kind="secondary",
            )
        )
    return tuple(actions)


@dataclass(frozen=True)
class KnowledgeServiceConfig:
    jwt_algorithm: str = "HS256"
    model_usage_monthly_token_budget: int = 0
    voyage_free_monthly_tokens: int = 0
    model_usage_counter_enabled: bool = True


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
        knowledge_repo_factory: KnowledgeRepositoryFactoryPort,
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
        _log_chunk_audit(logger, chunks, context="upload_normalized")
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
        knowledge_repo_factory: KnowledgeRepositoryFactoryPort,
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
        knowledge_repo_factory: KnowledgeRepositoryFactoryPort,
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

    async def processing_report(
        self,
        project_id: str,
        document_id: str,
        authorization: str | None,
        *,
        knowledge_repo_factory: KnowledgeRepositoryFactoryPort,
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

        batch_total = max((batch.batch_count for batch in batches), default=0)
        batch_completed = _batch_status_count(batches, "completed")
        batch_failed = _batch_status_count(batches, "failed")
        batch_processing = _batch_status_count(batches, "processing")
        batch_pending = _batch_status_count(batches, "pending")
        is_processing = document.status in {"processing"} or (
            document.preprocessing_status == "processing"
        )
        published_answer_count = int(document.structured_entries or 0)
        document_metrics = (
            dict(document.preprocessing_metrics)
            if isinstance(document.preprocessing_metrics, Mapping)
            else {}
        )
        answer_resolution_metrics = _answer_resolution_metrics(document_metrics)
        current_stage = str(document_metrics.get("stage") or "")
        answer_resolution_status = _answer_resolution_report_status(
            answer_resolution_metrics,
            is_processing=is_processing,
        )
        if (
            current_stage == "answer_resolution"
            and answer_resolution_status == "waiting"
        ):
            answer_resolution_status = "processing"
        answer_resolution_total = _json_int_metric(
            answer_resolution_metrics,
            "suspect_case_count",
        )
        answer_resolution_current = _json_int_metric(
            answer_resolution_metrics,
            "processed_case_count",
        )
        answer_resolution_final_count = (
            _json_int_metric(answer_resolution_metrics, "final_entry_count")
            or _json_int_metric(answer_resolution_metrics, "entry_count_after")
            or _json_int_metric(document_metrics, "canonical_entry_count")
            or _json_int_metric(document_metrics, "published_entry_count")
        )

        steps = (
            KnowledgeProcessingStepDto(
                id="prepare",
                label="Подготовка документа",
                status="completed"
                if batch_total > 0 or document.chunk_count > 0
                else "pending",
                current=document.chunk_count,
                total=document.chunk_count,
                message="Исходные части документа сохранены",
            ),
            KnowledgeProcessingStepDto(
                id="extract",
                label="Извлечение ответов",
                status=(
                    "failed"
                    if batch_failed > 0
                    else "completed"
                    if batch_total > 0 and batch_completed >= batch_total
                    else "processing"
                    if is_processing
                    else "pending"
                ),
                current=batch_completed,
                total=batch_total,
                message=f"Черновиков найдено: {candidate_summary.raw_count}",
            ),
            KnowledgeProcessingStepDto(
                id="answer_resolution",
                label="Разрешение ответов",
                status=answer_resolution_status,
                current=answer_resolution_current,
                total=answer_resolution_total,
                message=(
                    f"Проверено случаев: {answer_resolution_current} из {answer_resolution_total}"
                    if answer_resolution_total > 0
                    else "Ожидаем завершения извлечения"
                ),
            ),
            KnowledgeProcessingStepDto(
                id="publish",
                label="Публикация в базу знаний",
                status=(
                    "completed"
                    if published_answer_count > 0
                    else "waiting"
                    if current_stage == "answer_resolution" and is_processing
                    else "pending"
                ),
                current=published_answer_count,
                total=max(answer_resolution_final_count, published_answer_count),
                message=(
                    "Ожидаем завершения разрешения похожих ответов"
                    if current_stage == "answer_resolution" and is_processing
                    else f"Опубликовано ответов: {published_answer_count}"
                ),
            ),
        )

        metrics: JsonObject = {
            "source_chunk_count": _json_int_metric(
                document_metrics,
                "source_chunk_count",
            ),
            "raw_source_chunk_count": _json_int_metric(
                document_metrics,
                "raw_source_chunk_count",
            ),
            "markdown_semantic_units_total": _json_int_metric(
                document_metrics,
                "markdown_semantic_units_total",
            ),
            "markdown_child_sections_total": _json_int_metric(
                document_metrics,
                "markdown_child_sections_total",
            ),
            "canonical_entry_count": (
                _json_int_metric(document_metrics, "canonical_entry_count")
                or document.chunk_count
            ),
            "retrieval_surface_entry_count": document.structured_entries,
            "batch_total": batch_total,
            "batch_completed": batch_completed,
            "batch_failed": batch_failed,
            "batch_processing": batch_processing,
            "batch_pending": batch_pending,
            "draft_answer_count": candidate_summary.raw_count,
            "answer_candidate_count": candidate_summary.total_count,
            "published_answer_count": published_answer_count,
            "grounded_candidate_count": candidate_summary.grounded_count,
            "rejected_answer_count": candidate_summary.rejected_count,
            "tokens_input": sum(batch.tokens_input for batch in batches),
            "tokens_output": sum(batch.tokens_output for batch in batches),
            "tokens_total": sum(batch.tokens_total for batch in batches),
            "answer_resolution": answer_resolution_metrics,
        }

        if current_stage == "answer_resolution" and is_processing:
            title = "Разрешаем похожие ответы"
            message = (
                "Черновики уже сохранены. Сейчас система проверяет смысловые дубли "
                "и выбирает итоговые ответы перед публикацией."
            )
        elif current_stage == "answer_resolution_pending":
            title = "Проблемные части повторены"
            message = "Черновики готовы. Продолжите уплотнение и публикацию."
        else:
            title = (
                "Опубликовано частично: есть проблемные части"
                if batch_failed > 0 and published_answer_count > 0
                else _knowledge_processing_title(
                    document_status=document.status,
                    preprocessing_status=document.preprocessing_status or "",
                )
            )
            message = _knowledge_processing_message(
                batch_total=batch_total,
                batch_completed=batch_completed,
                batch_failed=batch_failed,
                raw_answer_count=candidate_summary.raw_count,
                published_answer_count=published_answer_count,
            )
        return KnowledgeProcessingReportDto(
            document_id=document_id,
            status=document.preprocessing_status or document.status,
            title=title,
            message=message,
            recoverable=batch_failed > 0
            or candidate_summary.raw_count > published_answer_count,
            steps=steps,
            actions=_knowledge_processing_actions(
                batch_failed=batch_failed,
                raw_answer_count=candidate_summary.raw_count,
                published_answer_count=published_answer_count,
                is_processing=is_processing,
                answer_resolution_ready=(
                    batch_total > 0
                    and batch_failed == 0
                    and batch_completed >= batch_total
                    and published_answer_count == 0
                ),
                current_stage=current_stage,
            ),
            metrics=metrics,
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
        knowledge_repo_factory: KnowledgeRepositoryFactoryPort,
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
        knowledge_repo_factory: KnowledgeRepositoryFactoryPort,
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

        return _normalize_chunks(raw_chunks)


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


def _normalize_chunks(raw_chunks: Sequence[object]) -> list[JsonObject]:
    chunks: list[JsonObject] = []
    for chunk in raw_chunks:
        normalized = _normalize_chunk(chunk)
        if normalized is not None:
            chunks.append(normalized)

    return chunks


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


def _is_present_chunk_value(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _chunk_field_counts(chunks: Sequence[JsonObject]) -> dict[str, int]:
    return {
        field: sum(1 for chunk in chunks if _is_present_chunk_value(chunk.get(field)))
        for field in _CHUNK_AUDIT_FIELDS
    }


def _chunk_unknown_field_counts(chunks: Sequence[JsonObject]) -> dict[str, int]:
    known = set(_CHUNK_AUDIT_FIELDS)
    counts: dict[str, int] = {}
    for chunk in chunks:
        for key, value in chunk.items():
            if key in known or not _is_present_chunk_value(value):
                continue
            counts[key] = counts.get(key, 0) + 1
    return counts


def _chunk_content_length_stats(chunks: Sequence[JsonObject]) -> JsonObject:
    lengths = [len(str(chunk.get("content") or "").strip()) for chunk in chunks]
    if not lengths:
        return {"min": 0, "max": 0, "avg": 0}
    return {
        "min": min(lengths),
        "max": max(lengths),
        "avg": round(sum(lengths) / len(lengths), 2),
    }


def _log_chunk_audit(
    logger: LoggerPort,
    chunks: Sequence[JsonObject],
    *,
    context: str,
) -> None:
    logger.info(
        "Knowledge upload chunk audit",
        extra={
            "context": context,
            "chunk_count": len(chunks),
            "field_counts": _chunk_field_counts(chunks),
            "unknown_field_counts": _chunk_unknown_field_counts(chunks),
            "content_length": _chunk_content_length_stats(chunks),
        },
    )


def _normalize_chunk(chunk: object) -> JsonObject | None:
    if isinstance(chunk, str):
        return _chunk_from_text(chunk)

    if isinstance(chunk, Mapping):
        return _chunk_from_mapping(chunk)

    return None


def _chunk_from_text(value: str) -> JsonObject | None:
    content = value.strip()
    return {"content": content} if content else None


def _chunk_from_mapping(value: Mapping[object, object]) -> JsonObject | None:
    content = str(value.get("content") or "").strip()
    if not content:
        return None

    normalized = {
        str(key): json_value_from_unknown(item) for key, item in value.items()
    }
    normalized["content"] = content
    return normalized
