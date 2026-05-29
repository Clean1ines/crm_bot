from __future__ import annotations

from src.application.errors import ValidationError
from src.application.services.knowledge_answer_compiler_batching import (
    _technical_chunk_batches_for_answer_compiler,
)
from src.application.services.knowledge_canonical_publication_builder import (
    canonical_entries_from_raw_answer_candidates as _canonical_entries_from_raw_answer_candidates,
)
from src.application.services.knowledge_ingestion_service import (
    CanonicalKnowledgeEntry,
    JsonObject,
    KnowledgeIngestionRepositoryFactoryPort,
    KnowledgePreprocessorFactoryPort,
    LoggerPort,
    ModelUsageRepositoryFactoryPort,
    _persist_stage_e_compiler_outputs,
    _raw_answer_candidates_from_preprocessing_entries,
)
from src.application.services.knowledge_source_material_builder import (
    _json_chunks_from_source_chunks,
)
from src.domain.project_plane.knowledge_preprocessing import (
    MODE_FAQ,
    PREPROCESSING_STATUS_COMPLETED,
    PREPROCESSING_STATUS_FAILED,
    PREPROCESSING_STATUS_PROCESSING,
    KnowledgePreprocessingValidationError,
    normalize_preprocessing_mode,
    prompt_version_for_mode,
)
from src.domain.project_plane.model_usage_views import ModelUsageEventCreate


class KnowledgeFailedBatchRetryService:
    def __init__(self, pool: object) -> None:
        self.pool = pool

    async def retry_failed_batches(
        self,
        *,
        project_id: str,
        document_id: str,
        knowledge_repo_factory: KnowledgeIngestionRepositoryFactoryPort,
        model_usage_repo_factory: ModelUsageRepositoryFactoryPort,
        preprocessor_factory: KnowledgePreprocessorFactoryPort,
        logger: LoggerPort,
    ) -> JsonObject:
        repo = knowledge_repo_factory(self.pool)
        usage_repo = model_usage_repo_factory(self.pool)
        document = await repo.get_document(document_id)
        if document is None or document.project_id != project_id:
            raise ValidationError("Knowledge document not found")

        mode = normalize_preprocessing_mode(document.preprocessing_mode)
        if mode == MODE_FAQ:
            raise KnowledgePreprocessingValidationError(
                "Legacy knowledge ingestion retry path is forbidden for mode=faq. "
                "Use Retrieval Surface Compilation pipeline."
            )

        source_chunks = await repo.list_document_source_chunks(
            project_id=project_id,
            document_id=document_id,
        )
        if not source_chunks:
            raise ValidationError("Knowledge document has no saved source chunks")

        batches = await repo.list_document_compiler_batches(
            project_id=project_id,
            document_id=document_id,
        )
        failed_batches = tuple(batch for batch in batches if batch.status == "failed")
        if not failed_batches:
            return {
                "status": "skipped",
                "reason": "no_failed_batches",
                "document_id": document_id,
            }

        source_json_chunks = _json_chunks_from_source_chunks(source_chunks)
        technical_batches = tuple(
            _technical_chunk_batches_for_answer_compiler(source_json_chunks)
        )
        preprocessor = preprocessor_factory()
        await repo.update_document_preprocessing_status(
            document_id,
            mode=mode,
            status=PREPROCESSING_STATUS_PROCESSING,
            model=preprocessor.model_name,
            prompt_version=prompt_version_for_mode(mode),
            metrics={
                "stage": "retry_failed_batches",
                "failed_batch_count_before": len(failed_batches),
            },
        )
        await repo.update_document_status(document_id, "processing")
        usage_event_count = 0
        retried_batch_count = 0

        for batch in failed_batches:
            if batch.batch_index < 1 or batch.batch_index > len(technical_batches):
                await repo.fail_compiler_batch(
                    batch.id,
                    error_type="ValidationError",
                    error_message="Saved compiler batch index is outside reconstructed technical batch range",
                )
                continue

            technical_chunks = technical_batches[batch.batch_index - 1]
            await repo.mark_compiler_batch_processing(
                batch.id,
                attempt_count=batch.attempt_count + 1,
            )
            try:
                execution = await preprocessor.preprocess(
                    mode=mode,
                    chunks=technical_chunks,
                    file_name=document.file_name,
                )
                if execution.usage is not None:
                    await usage_repo.record_event(
                        ModelUsageEventCreate.from_measurement(
                            project_id=project_id,
                            source="knowledge_preprocessing",
                            measurement=execution.usage,
                            document_id=document_id,
                        )
                    )
                    usage_event_count += 1

                safe_entries = tuple(execution.result.entries)
                raw_candidates = _raw_answer_candidates_from_preprocessing_entries(
                    project_id=project_id,
                    document_id=document_id,
                    compiler_run_id=batch.compiler_run_id,
                    batch_id=batch.id,
                    batch_index=batch.batch_index,
                    entries=safe_entries,
                    source_chunks=source_chunks,
                    mode=mode,
                )
                await repo.delete_raw_answer_candidates_for_batch(
                    project_id=project_id,
                    document_id=document_id,
                    batch_id=batch.id,
                )
                await repo.add_answer_candidates(
                    project_id=project_id,
                    document_id=document_id,
                    candidates=raw_candidates,
                )
                usage = execution.usage
                await repo.complete_compiler_batch(
                    batch.id,
                    model=execution.result.model,
                    prompt_version=execution.result.prompt_version,
                    tokens_input=usage.tokens_input if usage is not None else 0,
                    tokens_output=usage.tokens_output
                    if usage is not None and usage.tokens_output is not None
                    else 0,
                    tokens_total=usage.tokens_total if usage is not None else 0,
                )
                retried_batch_count += 1
            except Exception as exc:
                error_message = str(exc)[:500] or type(exc).__name__
                await repo.fail_compiler_batch(
                    batch.id,
                    error_type=type(exc).__name__,
                    error_message=error_message,
                )
                await repo.update_document_preprocessing_status(
                    document_id,
                    mode=mode,
                    status=PREPROCESSING_STATUS_FAILED,
                    error=error_message,
                    model=preprocessor.model_name,
                    prompt_version=prompt_version_for_mode(mode),
                    metrics={
                        "stage": "retry_failed_batches",
                        "status_message": (
                            "Повтор проблемной части завершился ошибкой"
                        ),
                        "error_type": type(exc).__name__,
                        "retried_batch_count": retried_batch_count,
                        "failed_batch_count_before": len(failed_batches),
                        "usage_event_count": usage_event_count,
                    },
                )
                await repo.update_document_status(document_id, "error", error_message)
                raise

        updated_batches = await repo.list_document_compiler_batches(
            project_id=project_id,
            document_id=document_id,
        )
        remaining_failed_count = sum(
            1 for batch in updated_batches if batch.status == "failed"
        )
        all_batches_completed = bool(updated_batches) and all(
            batch.status == "completed" for batch in updated_batches
        )
        raw_candidates = await repo.list_document_raw_answer_candidates(
            project_id=project_id,
            document_id=document_id,
        )
        canonical_entries: tuple[CanonicalKnowledgeEntry, ...] = ()

        if all_batches_completed:
            canonical_entries = _canonical_entries_from_raw_answer_candidates(
                project_id=project_id,
                document_id=document_id,
                compiler_run_id=updated_batches[0].compiler_run_id,
                mode=mode,
                candidates=raw_candidates,
            )
            if not canonical_entries:
                raise ValidationError(
                    "Knowledge retry produced no grounded answer entries"
                )
            await _persist_stage_e_compiler_outputs(
                repo=repo,
                project_id=project_id,
                document_id=document_id,
                compiler_run_id=updated_batches[0].compiler_run_id,
                source_chunks=source_chunks,
                entries=canonical_entries,
            )

        metrics: JsonObject = {
            "stage": "retry_failed_batches",
            "retried_batch_count": retried_batch_count,
            "failed_batch_count_before": len(failed_batches),
            "remaining_failed_batch_count": remaining_failed_count,
            "usage_event_count": usage_event_count,
            "raw_answer_count": len(raw_candidates),
            "canonical_entry_count": len(canonical_entries),
        }
        if all_batches_completed:
            metrics["status_message"] = (
                "Проблемные части повторены, ответы опубликованы"
            )
            await repo.update_document_preprocessing_status(
                document_id,
                mode=mode,
                status=PREPROCESSING_STATUS_COMPLETED,
                model=preprocessor.model_name,
                prompt_version=prompt_version_for_mode(mode),
                metrics=metrics,
            )
            await repo.update_document_status(document_id, "processed")
        else:
            metrics["status_message"] = (
                "Часть проблемных частей всё ещё требует повтора"
            )
            await repo.update_document_preprocessing_status(
                document_id,
                mode=mode,
                status=PREPROCESSING_STATUS_FAILED,
                model=preprocessor.model_name,
                prompt_version=prompt_version_for_mode(mode),
                metrics=metrics,
            )
            await repo.update_document_status(
                document_id,
                "error",
                "Some compiler batches still failed after retry",
            )
        logger.info(
            "Knowledge failed compiler batches retried",
            extra={
                "project_id": project_id,
                "document_id": document_id,
                "retried_batch_count": retried_batch_count,
                "remaining_failed_batch_count": remaining_failed_count,
            },
        )
        return {
            "status": "completed" if all_batches_completed else "partial",
            "document_id": document_id,
            "retried_batch_count": retried_batch_count,
            "remaining_failed_batch_count": remaining_failed_count,
            "usage_event_count": usage_event_count,
        }
