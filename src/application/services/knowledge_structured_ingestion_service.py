from __future__ import annotations

import asyncio
import time

from src.application.errors import (
    EmbeddingProviderError,
    KnowledgeDocumentDeletedDuringProcessingError,
    ValidationError,
)
from src.application.services.commercial_price_ingestion_service import (
    CommercialPriceIngestionService,
)
from src.application.ports.knowledge.structured_ingestion import (
    KnowledgeStructuredIngestionRepositoryFactoryPort,
)
from src.application.services.knowledge_answer_compiler_batching import (
    KCD_STAGE_K_TECHNICAL_CHUNKS_PER_LLM_CALL,
    KCD_STAGE_K_TECHNICAL_SOURCE_CHAR_BUDGET,
    build_technical_chunk_batches_for_answer_compiler,
)
from src.application.services.knowledge_answer_resolution_service import (
    KnowledgeAnswerResolutionService,
)
from src.application.services.knowledge_canonical_publication_builder import (
    canonical_entries_from_preprocessing_result as _canonical_entries_from_preprocessing_result,
)
from src.application.services.knowledge_generated_entry_repair import (
    repair_generated_entry as _repair_generated_entry,
)
from src.application.ports.knowledge_port import (
    KnowledgePreprocessorFactoryPort,
    ModelUsageRepositoryFactoryPort,
)
from src.application.ports.logger_port import LoggerPort
from src.application.services.knowledge_answer_candidate_builder import (
    build_raw_answer_candidates_from_preprocessing_entries,
)
from src.application.services.knowledge_compiled_entry_cleanup import (
    cleanup_compiled_entries_mechanically,
    source_excerpts_from_preprocessing_entry,
)
from src.application.services.knowledge_compiler_batch_builder import (
    KCD_STAGE_K_CANCELLED_ERROR,
    KCD_STAGE_K_COMPILER_VERSION,
    KCD_STAGE_K_EXTRACTION_CONCURRENCY_DEFAULT,
    build_compiler_batches_from_technical_batches,
    build_stage_e_compiler_run,
    build_stage_e_compiler_run_id,
)
from src.application.services.knowledge_ingestion_contracts import (
    CommercialPriceAcquisitionServiceFactoryPort,
    CommercialPriceRepositoryFactoryPort,
    KnowledgeDocumentProcessingResult,
)
from src.application.services.knowledge_preprocessing_result_helpers import (
    json_metric_int,
    build_preprocessing_failure_status_message,
    build_preprocessing_result_from_entries,
    source_excerpt_to_text,
)
from src.application.services.knowledge_retighten_planner import (
    _existing_project_titles_for_answer_resolution,
)
from src.application.services.knowledge_stage_e_publication_helpers import (
    persist_stage_e_compiler_outputs,
)
from src.domain.project_plane.json_types import JsonObject
from src.domain.project_plane.knowledge_compilation import CompilerBatch
from src.domain.project_plane.knowledge_preprocessing import (
    KnowledgePreprocessingEntry,
    KnowledgePreprocessingMode,
    KnowledgePreprocessingResult,
)
from src.application.services.knowledge_source_material_builder import (
    build_compiler_source_chunks_for_preprocessing,
    filter_indexable_chunks,
    is_markdown_file,
    count_json_array_field_items,
    build_source_chunks_from_json_chunks,
)
from src.domain.project_plane.knowledge_artifact_cleanup import (
    build_document_reset_cleanup_plan,
)
from src.domain.project_plane.knowledge_preprocessing import (
    MODE_FAQ,
    MODE_PRICE_LIST,
    PREPROCESSING_STATUS_COMPLETED,
    PREPROCESSING_STATUS_FAILED,
    PREPROCESSING_STATUS_PROCESSING,
    KnowledgePreprocessingValidationError,
    prompt_version_for_mode,
)
from src.domain.project_plane.model_usage_views import ModelUsageEventCreate


class KnowledgeStructuredIngestionService:
    def __init__(self, pool: object) -> None:
        self.pool = pool

    async def process_document(
        self,
        *,
        project_id: str,
        document_id: str,
        file_name: str,
        chunks: list[JsonObject],
        mode: KnowledgePreprocessingMode,
        knowledge_repo_factory: KnowledgeStructuredIngestionRepositoryFactoryPort,
        model_usage_repo_factory: ModelUsageRepositoryFactoryPort,
        preprocessor_factory: KnowledgePreprocessorFactoryPort | None,
        logger: LoggerPort,
        commercial_price_repo_factory: CommercialPriceRepositoryFactoryPort
        | None = None,
        commercial_price_acquisition_service_factory: CommercialPriceAcquisitionServiceFactoryPort
        | None = None,
    ) -> KnowledgeDocumentProcessingResult:
        repo = knowledge_repo_factory(self.pool)
        usage_repo = model_usage_repo_factory(self.pool)
        await repo.cleanup_document_artifacts(
            build_document_reset_cleanup_plan(
                project_id=project_id,
                document_id=document_id,
            )
        )

        indexable_chunks = filter_indexable_chunks(chunks)
        if not indexable_chunks:
            message = "No indexable knowledge chunks after filtering"
            await repo.update_document_status(document_id, "error", message)
            raise ValidationError(message)

        compiler_source_chunks = build_compiler_source_chunks_for_preprocessing(
            file_name=file_name,
            chunks=indexable_chunks,
            mode=mode,
        )
        source_chunks = build_source_chunks_from_json_chunks(
            project_id=project_id,
            document_id=document_id,
            chunks=indexable_chunks,
        )
        if mode == MODE_PRICE_LIST and commercial_price_repo_factory is not None:
            price_result = (
                await CommercialPriceIngestionService().persist_price_source_material(
                    project_id=project_id,
                    knowledge_document_id=document_id,
                    file_name=file_name,
                    chunks=indexable_chunks,
                    price_repo=commercial_price_repo_factory(self.pool),
                    acquisition_service=(
                        commercial_price_acquisition_service_factory()
                        if commercial_price_acquisition_service_factory is not None
                        else None
                    ),
                )
            )
            logger.info(
                "Commercial price source material persisted",
                extra={
                    "project_id": project_id,
                    "document_id": document_id,
                    "price_document_id": price_result.price_document_id,
                    "price_source_unit_count": price_result.source_unit_count,
                    "price_document_status": price_result.status.value,
                    "price_acquisition_row_count": price_result.acquisition_row_count,
                    "price_acquisition_fact_candidate_count": price_result.acquisition_fact_candidate_count,
                    "price_acquisition_issue_count": price_result.acquisition_issue_count,
                },
            )

        compiler_run_id = build_stage_e_compiler_run_id(
            document_id=document_id, mode=mode
        )
        await repo.create_compiler_run(
            build_stage_e_compiler_run(
                project_id=project_id,
                document_id=document_id,
                mode=mode,
                source_chunk_count=len(source_chunks),
            )
        )

        if preprocessor_factory is None:
            raise ValidationError(
                "Knowledge preprocessing adapter is required for price_list uploads"
            )

        await repo.add_source_chunks(
            project_id=project_id,
            document_id=document_id,
            chunks=source_chunks,
        )

        if mode == MODE_FAQ:
            raise KnowledgePreprocessingValidationError(
                "Legacy knowledge ingestion preprocessor path is forbidden for mode=faq. "
                "Use Retrieval Surface Compilation pipeline."
            )

        await repo.update_document_preprocessing_status(
            document_id,
            mode=mode,
            status=PREPROCESSING_STATUS_PROCESSING,
        )

        active_model = ""
        active_prompt_version = prompt_version_for_mode(mode)
        technical_batches: tuple[list[JsonObject], ...] = ()

        try:
            preprocessor = preprocessor_factory()
            active_model = preprocessor.model_name
            technical_batches = tuple(
                build_technical_chunk_batches_for_answer_compiler(
                    compiler_source_chunks
                )
            )
            compiler_batches = build_compiler_batches_from_technical_batches(
                project_id=project_id,
                document_id=document_id,
                compiler_run_id=compiler_run_id,
                technical_batches=technical_batches,
                source_chunks=source_chunks,
            )
            await repo.create_compiler_batches(
                project_id=project_id,
                document_id=document_id,
                batches=compiler_batches,
            )
            preprocessing_results: list[KnowledgePreprocessingResult] = []
            compiled_entries: list[KnowledgePreprocessingEntry] = []
            usage_event_count = 0
            llm_answer_resolution_call_count = 0
            answer_resolution_keep_separate_count = 0
            latest_result: KnowledgePreprocessingResult | None = None
            processing_started_monotonic = time.monotonic()

            await repo.update_document_preprocessing_status(
                document_id,
                mode=mode,
                status=PREPROCESSING_STATUS_PROCESSING,
                model=active_model,
                prompt_version=active_prompt_version,
                metrics={
                    "answer_compiler": KCD_STAGE_K_COMPILER_VERSION,
                    "stage": "technical_compiler_loop",
                    "status_message": (
                        "Извлекаем смысловые ответы из документа и "
                        "привязываем их к источнику"
                    ),
                    "model": active_model,
                    "prompt_version": active_prompt_version,
                    "source_chunk_count": len(compiler_source_chunks),
                    "raw_source_chunk_count": len(indexable_chunks),
                    "markdown_semantic_units_total": (
                        len(compiler_source_chunks)
                        if is_markdown_file(file_name)
                        else 0
                    ),
                    "markdown_semantic_units_processed": 0,
                    "markdown_child_sections_total": (
                        count_json_array_field_items(
                            compiler_source_chunks,
                            "children",
                        )
                        if is_markdown_file(file_name)
                        else 0
                    ),
                    "markdown_section_aware_batching": is_markdown_file(file_name),
                    "technical_compiler_total_count": len(technical_batches),
                    "technical_source_char_budget": (
                        KCD_STAGE_K_TECHNICAL_SOURCE_CHAR_BUDGET
                    ),
                    "technical_compiler_call_count": 0,
                    "technical_chunk_processed_count": 0,
                    "technical_chunk_total_count": len(technical_batches),
                    "compiled_entry_count": 0,
                    "semantic_answer_count": 0,
                    "incoming_entry_count": 0,
                    "extraction_concurrency": KCD_STAGE_K_EXTRACTION_CONCURRENCY_DEFAULT,
                    "llm_answer_resolution_call_count": 0,
                    "semantic_answer_resolution_count": 0,
                    "answer_resolution_call_count": 0,
                    "usage_event_count": 0,
                    "elapsed_seconds": 0,
                    "previous_title_carryover": False,
                    "one_answer_at_a_time_resolution": False,
                    "answer_resolution_enabled": True,
                    "source_refs_preserved_per_semantic_entry": True,
                    "row_explosion_guard": (
                        "raw_source_chunks_not_persisted_as_runtime_entries"
                    ),
                },
            )

            progress_lock = asyncio.Lock()
            completed_batch_count = 0
            failed_batch_count = 0
            raw_candidate_count = 0
            entries_by_batch_index: dict[
                int, tuple[KnowledgePreprocessingEntry, ...]
            ] = {}
            results_by_batch_index: dict[int, KnowledgePreprocessingResult] = {}
            extraction_concurrency = KCD_STAGE_K_EXTRACTION_CONCURRENCY_DEFAULT
            extraction_semaphore = asyncio.Semaphore(extraction_concurrency)

            async def process_compiler_batch(
                batch_index: int,
                technical_chunks: list[JsonObject],
                compiler_batch: CompilerBatch,
            ) -> None:
                nonlocal completed_batch_count
                nonlocal failed_batch_count
                nonlocal raw_candidate_count
                nonlocal usage_event_count
                nonlocal latest_result

                async with extraction_semaphore:
                    if await repo.is_document_processing_cancelled(document_id):
                        raise RuntimeError(KCD_STAGE_K_CANCELLED_ERROR)

                    await repo.mark_compiler_batch_processing(
                        compiler_batch.id,
                        attempt_count=compiler_batch.attempt_count + 1,
                    )

                    try:
                        execution = await preprocessor.preprocess(
                            mode=mode,
                            chunks=technical_chunks,
                            file_name=file_name,
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

                        if await repo.is_document_processing_cancelled(document_id):
                            logger.info(
                                "Knowledge answer compiler batch result dropped after cancellation",
                                extra={
                                    "project_id": project_id,
                                    "document_id": document_id,
                                    "batch_index": batch_index,
                                    "batch_count": len(technical_batches),
                                    "model": execution.result.model,
                                    "requested_model": active_model,
                                },
                            )
                            raise RuntimeError(KCD_STAGE_K_CANCELLED_ERROR)

                        actual_model = execution.result.model
                        safe_entries = list(execution.result.entries)

                        raw_candidates = (
                            build_raw_answer_candidates_from_preprocessing_entries(
                                project_id=project_id,
                                document_id=document_id,
                                compiler_run_id=compiler_run_id,
                                batch_id=compiler_batch.id,
                                batch_index=batch_index,
                                entries=safe_entries,
                                source_chunks=source_chunks,
                                mode=mode,
                            )
                        )
                        await repo.add_answer_candidates(
                            project_id=project_id,
                            document_id=document_id,
                            candidates=raw_candidates,
                        )
                        usage = execution.usage
                        await repo.complete_compiler_batch(
                            compiler_batch.id,
                            model=execution.result.model,
                            prompt_version=execution.result.prompt_version,
                            tokens_input=usage.tokens_input if usage is not None else 0,
                            tokens_output=usage.tokens_output
                            if usage is not None and usage.tokens_output is not None
                            else 0,
                            tokens_total=usage.tokens_total if usage is not None else 0,
                        )
                    except Exception as exc:
                        if str(exc) == KCD_STAGE_K_CANCELLED_ERROR or (
                            await repo.is_document_processing_cancelled(document_id)
                        ):
                            raise RuntimeError(KCD_STAGE_K_CANCELLED_ERROR) from exc

                        await repo.fail_compiler_batch(
                            compiler_batch.id,
                            error_type=type(exc).__name__,
                            error_message=str(exc)[:500] or type(exc).__name__,
                        )
                        async with progress_lock:
                            failed_batch_count += 1
                            progress_metrics: JsonObject = {
                                "answer_compiler": KCD_STAGE_K_COMPILER_VERSION,
                                "stage": "technical_compiler_loop",
                                "status_message": (
                                    "Обработка части завершилась с ошибкой; "
                                    "сохранённые черновики остаются доступными"
                                ),
                                "model": active_model,
                                "prompt_version": active_prompt_version,
                                "source_chunk_count": len(indexable_chunks),
                                "technical_compiler_total_count": len(
                                    technical_batches
                                ),
                                "technical_compiler_call_count": completed_batch_count,
                                "technical_chunk_processed_count": completed_batch_count,
                                "technical_chunk_total_count": len(technical_batches),
                                "failed_part_count": failed_batch_count,
                                "raw_draft_count": raw_candidate_count,
                                "compiled_entry_count": sum(
                                    len(entries)
                                    for entries in entries_by_batch_index.values()
                                ),
                                "answer_resolution_enabled": True,
                                "extraction_concurrency": extraction_concurrency,
                                "elapsed_seconds": round(
                                    time.monotonic() - processing_started_monotonic,
                                    1,
                                ),
                            }
                            await repo.update_document_preprocessing_status(
                                document_id,
                                mode=mode,
                                status=PREPROCESSING_STATUS_PROCESSING,
                                model=active_model,
                                prompt_version=active_prompt_version,
                                metrics=progress_metrics,
                            )
                        logger.warning(
                            "Knowledge answer compiler technical batch failed",
                            extra={
                                "project_id": project_id,
                                "document_id": document_id,
                                "batch_index": batch_index,
                                "batch_count": len(technical_batches),
                                "error_type": type(exc).__name__,
                            },
                        )
                        raise

                    async with progress_lock:
                        completed_batch_count += 1
                        raw_candidate_count += len(raw_candidates)
                        if execution.usage is not None:
                            usage_event_count += 1
                        latest_result = execution.result
                        preprocessing_results.append(execution.result)
                        results_by_batch_index[batch_index] = execution.result
                        entries_by_batch_index[batch_index] = tuple(safe_entries)
                        compiled_count = sum(
                            len(entries) for entries in entries_by_batch_index.values()
                        )
                        progress_metrics = {
                            "answer_compiler": KCD_STAGE_K_COMPILER_VERSION,
                            "stage": "technical_compiler_loop",
                            "status_message": (
                                "Документ разбирается. Черновики сохраняются "
                                "после каждого шага."
                            ),
                            "model": actual_model,
                            "requested_model": active_model,
                            "actual_model": actual_model,
                            "prompt_version": active_prompt_version,
                            "source_chunk_count": len(compiler_source_chunks),
                            "raw_source_chunk_count": len(indexable_chunks),
                            "markdown_semantic_units_total": (
                                len(compiler_source_chunks)
                                if is_markdown_file(file_name)
                                else 0
                            ),
                            "markdown_semantic_units_processed": completed_batch_count,
                            "markdown_section_aware_batching": is_markdown_file(
                                file_name
                            ),
                            "technical_compiler_total_count": len(technical_batches),
                            "technical_source_char_budget": (
                                KCD_STAGE_K_TECHNICAL_SOURCE_CHAR_BUDGET
                            ),
                            "technical_compiler_call_count": completed_batch_count,
                            "technical_chunk_processed_count": completed_batch_count,
                            "technical_chunk_total_count": len(technical_batches),
                            "failed_part_count": failed_batch_count,
                            "raw_draft_count": raw_candidate_count,
                            "compiled_entry_count": compiled_count,
                            "semantic_answer_count": compiled_count,
                            "incoming_entry_count": len(execution.result.entries),
                            "llm_answer_resolution_call_count": llm_answer_resolution_call_count,
                            "semantic_answer_resolution_count": llm_answer_resolution_call_count,
                            "answer_resolution_call_count": llm_answer_resolution_call_count,
                            "answer_resolution_keep_separate_count": (
                                answer_resolution_keep_separate_count
                            ),
                            "usage_event_count": usage_event_count,
                            "answer_resolution_enabled": True,
                            "extraction_concurrency": extraction_concurrency,
                            "source_refs_preserved_per_semantic_entry": True,
                            "row_explosion_guard": (
                                "raw_source_chunks_not_persisted_as_runtime_entries"
                            ),
                            "elapsed_seconds": round(
                                time.monotonic() - processing_started_monotonic,
                                1,
                            ),
                        }
                        logger.info(
                            "Knowledge answer compiler technical batch completed",
                            extra={
                                "project_id": project_id,
                                "document_id": document_id,
                                "batch_index": batch_index,
                                "batch_count": len(technical_batches),
                                "extraction_status": "completed",
                                "raw_candidates_count": len(raw_candidates),
                                "compiled_entry_count": compiled_count,
                                "tokens": execution.usage.tokens_total
                                if execution.usage is not None
                                else 0,
                                "elapsed_seconds": progress_metrics["elapsed_seconds"],
                                "model": actual_model,
                                "requested_model": active_model,
                                "actual_model": actual_model,
                            },
                        )
                        await repo.update_document_preprocessing_status(
                            document_id,
                            mode=mode,
                            status=PREPROCESSING_STATUS_PROCESSING,
                            model=actual_model,
                            prompt_version=active_prompt_version,
                            metrics=progress_metrics,
                        )

            batch_tasks = [
                asyncio.create_task(
                    process_compiler_batch(
                        batch_index,
                        technical_chunks,
                        compiler_batches[batch_index - 1],
                    )
                )
                for batch_index, technical_chunks in enumerate(
                    technical_batches, start=1
                )
            ]
            batch_task_results = await asyncio.gather(
                *batch_tasks, return_exceptions=True
            )
            batch_errors = [
                result for result in batch_task_results if isinstance(result, Exception)
            ]
            if batch_errors:
                raise batch_errors[0]

            compiled_entries = [
                entry
                for batch_index in sorted(entries_by_batch_index)
                for entry in entries_by_batch_index[batch_index]
            ]
            latest_result = (
                results_by_batch_index[max(results_by_batch_index)]
                if results_by_batch_index
                else latest_result
            )

            if await repo.is_document_processing_cancelled(document_id):
                raise RuntimeError(KCD_STAGE_K_CANCELLED_ERROR)

            if latest_result is None:
                raise ValidationError("Knowledge preprocessing produced no results")

            source_excerpts_before_cleanup = tuple(
                source_excerpts_from_preprocessing_entry(entry)
                for entry in compiled_entries
            )
            cleanup_result = cleanup_compiled_entries_mechanically(
                entries=compiled_entries,
                source_excerpts_by_entry=source_excerpts_before_cleanup,
            )
            existing_project_titles = (
                await _existing_project_titles_for_answer_resolution(
                    repo=repo,
                    project_id=project_id,
                    document_id=document_id,
                )
            )
            await repo.update_document_preprocessing_status(
                document_id,
                mode=mode,
                status=PREPROCESSING_STATUS_PROCESSING,
                model=active_model,
                prompt_version=active_prompt_version,
                metrics={
                    "answer_compiler": KCD_STAGE_K_COMPILER_VERSION,
                    "stage": "answer_resolution",
                    "status_message": (
                        "Извлечение завершено, идёт уплотнение повторяющихся смыслов."
                    ),
                    "technical_chunk_processed_count": len(technical_batches),
                    "technical_chunk_total_count": len(technical_batches),
                    "failed_part_count": 0,
                    "raw_draft_count": raw_candidate_count,
                    "compiled_entry_count": len(cleanup_result.entries),
                    "answer_resolution_enabled": True,
                    "extraction_concurrency": extraction_concurrency,
                    **cleanup_result.metrics,
                    "elapsed_seconds": round(
                        time.monotonic() - processing_started_monotonic,
                        1,
                    ),
                },
            )

            async def persist_answer_resolution_progress(metrics: JsonObject) -> None:
                await repo.update_document_preprocessing_status(
                    document_id,
                    mode=mode,
                    status=PREPROCESSING_STATUS_PROCESSING,
                    model=active_model,
                    prompt_version=active_prompt_version,
                    metrics={
                        "answer_compiler": KCD_STAGE_K_COMPILER_VERSION,
                        "stage": "answer_resolution",
                        "status_message": (
                            "Черновики сохранены, идёт разрешение похожих ответов."
                        ),
                        "technical_chunk_processed_count": len(technical_batches),
                        "technical_chunk_total_count": len(technical_batches),
                        "failed_part_count": 0,
                        "raw_draft_count": raw_candidate_count,
                        "compiled_entry_count": len(cleanup_result.entries),
                        "deterministic_cleanup": cleanup_result.metrics,
                        "answer_resolution": {
                            **metrics,
                            "raw_draft_count": raw_candidate_count,
                        },
                        "answer_resolution_fallback_published": (
                            metrics.get("fallback_published") is True
                        ),
                        "answer_resolution_enabled": True,
                        "extraction_concurrency": extraction_concurrency,
                        "elapsed_seconds": round(
                            time.monotonic() - processing_started_monotonic,
                            1,
                        ),
                    },
                )

            answer_resolution_result = (
                await KnowledgeAnswerResolutionService().resolve_compiled_answer_cases(
                    preprocessor=preprocessor,
                    mode=mode,
                    file_name=file_name,
                    entries=cleanup_result.entries,
                    source_excerpts_by_entry=cleanup_result.source_excerpts_by_entry,
                    existing_project_titles=existing_project_titles,
                    on_progress=persist_answer_resolution_progress,
                )
            )
            tightened_entries = answer_resolution_result.entries
            tightened_source_excerpts = (
                answer_resolution_result.source_excerpts_by_entry
            )
            answer_resolution_metrics = answer_resolution_result.metrics
            regenerated_entries: list[KnowledgePreprocessingEntry] = []
            generated_entry_repair_warnings: list[tuple[str, ...]] = []
            for idx, generated_entry in enumerate(tightened_entries):
                raw_source_excerpt = (
                    tightened_source_excerpts[idx]
                    if idx < len(tightened_source_excerpts)
                    else (generated_entry.source_excerpt,)
                )
                source_text = source_excerpt_to_text(raw_source_excerpt)
                repaired_entry, repair_warnings = _repair_generated_entry(
                    generated_entry,
                    source_excerpt=source_text,
                )
                regenerated_entries.append(repaired_entry)
                generated_entry_repair_warnings.append(repair_warnings)
            tightened_entries = tuple(regenerated_entries)
            answer_resolution_fallback_published = (
                answer_resolution_metrics.get("fallback_published") is True
            )
            if answer_resolution_fallback_published:
                answer_resolution_metrics["status"] = "failed_fallback_published"
                answer_resolution_metrics["published_fallback_entry_count"] = len(
                    tightened_entries
                )
                answer_resolution_metrics["raw_draft_count"] = raw_candidate_count
            llm_answer_resolution_call_count = json_metric_int(
                answer_resolution_metrics, "llm_call_count"
            )
            answer_resolution_keep_separate_count = json_metric_int(
                answer_resolution_metrics, "kept_separate_count"
            )

            result = build_preprocessing_result_from_entries(
                mode=mode,
                template=latest_result,
                entries=tightened_entries,
                metrics={
                    "technical_compiler_call_count": len(preprocessing_results),
                    "technical_chunk_batch_size": (
                        KCD_STAGE_K_TECHNICAL_CHUNKS_PER_LLM_CALL
                    ),
                    "technical_source_char_budget": (
                        KCD_STAGE_K_TECHNICAL_SOURCE_CHAR_BUDGET
                    ),
                    "llm_answer_resolution_call_count": llm_answer_resolution_call_count,
                    "answer_resolution_keep_separate_count": (
                        answer_resolution_keep_separate_count
                    ),
                    "compiled_entry_key_count": len(tightened_entries),
                    "raw_draft_count": raw_candidate_count,
                    "deterministic_cleanup": cleanup_result.metrics,
                    "merged_preprocessing_entry_counts": cleanup_result.metrics.get(
                        "merged_preprocessing_entry_counts", []
                    ),
                    "source_refs_preserved_per_semantic_entry": True,
                    "answer_resolution": answer_resolution_metrics,
                    "answer_resolution_fallback_published": answer_resolution_fallback_published,
                    "answer_resolution_enabled": True,
                    "extraction_concurrency": extraction_concurrency,
                    "generated_entry_repair_warnings": [
                        list(item) for item in generated_entry_repair_warnings if item
                    ],
                },
            )
            canonical_entries = _canonical_entries_from_preprocessing_result(
                project_id=project_id,
                document_id=document_id,
                compiler_run_id=compiler_run_id,
                result=result,
                source_chunks=source_chunks,
            )
            if not canonical_entries:
                raise ValidationError(
                    "Knowledge preprocessing produced no grounded answer entries"
                )

            logger.info(
                "Knowledge answer compiler persistence audit",
                extra={
                    "project_id": project_id,
                    "document_id": document_id,
                    "context": f"{mode}_answer_compiler_upload",
                    "source_chunk_count": len(source_chunks),
                    "llm_entry_count": len(result.entries),
                    "canonical_entry_count": len(canonical_entries),
                    "row_explosion_guard": (
                        "raw_source_chunks_not_persisted_as_runtime_entries"
                    ),
                    "metadata_preserved": True,
                    "source_refs_preserved_per_semantic_entry": True,
                },
            )

            await persist_stage_e_compiler_outputs(
                repo=repo,
                project_id=project_id,
                document_id=document_id,
                compiler_run_id=compiler_run_id,
                source_chunks=source_chunks,
                entries=canonical_entries,
            )

            preprocessing_metrics: JsonObject = dict(result.metrics)
            preprocessing_metrics["raw_source_chunk_count"] = len(indexable_chunks)
            preprocessing_metrics["markdown_semantic_units_total"] = (
                len(compiler_source_chunks) if is_markdown_file(file_name) else 0
            )
            preprocessing_metrics["markdown_semantic_units_processed"] = (
                len(compiler_source_chunks) if is_markdown_file(file_name) else 0
            )
            preprocessing_metrics["markdown_child_sections_total"] = (
                count_json_array_field_items(
                    compiler_source_chunks,
                    "children",
                )
                if is_markdown_file(file_name)
                else 0
            )
            preprocessing_metrics["markdown_section_aware_batching"] = is_markdown_file(
                file_name
            )
            preprocessing_metrics["llm_entry_count"] = len(result.entries)
            preprocessing_metrics["canonical_entry_count"] = len(canonical_entries)
            preprocessing_metrics["answer_compiler"] = KCD_STAGE_K_COMPILER_VERSION
            preprocessing_metrics["technical_compiler_call_count"] = len(
                preprocessing_results
            )
            preprocessing_metrics["technical_compiler_total_count"] = len(
                technical_batches
            )
            preprocessing_metrics["technical_chunk_total_count"] = len(
                technical_batches
            )
            preprocessing_metrics["technical_chunk_processed_count"] = len(
                technical_batches
            )
            preprocessing_metrics["semantic_answer_count"] = len(canonical_entries)
            preprocessing_metrics["published_entry_count"] = len(canonical_entries)
            preprocessing_metrics["model"] = result.model
            preprocessing_metrics["requested_model"] = active_model
            preprocessing_metrics["actual_model"] = result.model
            preprocessing_metrics["prompt_version"] = active_prompt_version
            preprocessing_metrics["stage"] = "completed"
            preprocessing_metrics["status_message"] = (
                "База знаний обновлена. Сырые черновики сохранены для проверки."
            )
            preprocessing_metrics["usage_event_count"] = usage_event_count
            preprocessing_metrics["llm_answer_resolution_call_count"] = (
                llm_answer_resolution_call_count
            )
            preprocessing_metrics["semantic_answer_resolution_count"] = (
                llm_answer_resolution_call_count
            )
            preprocessing_metrics["answer_resolution_call_count"] = (
                llm_answer_resolution_call_count
            )
            preprocessing_metrics["answer_resolution_keep_separate_count"] = (
                answer_resolution_keep_separate_count
            )
            preprocessing_metrics["elapsed_seconds"] = round(
                time.monotonic() - processing_started_monotonic,
                1,
            )
            preprocessing_metrics["previous_title_carryover"] = False
            preprocessing_metrics["one_answer_at_a_time_resolution"] = False
            preprocessing_metrics["one_meaning_at_a_time_extraction"] = True
            preprocessing_metrics["answer_resolution_enabled"] = True
            preprocessing_metrics["extraction_concurrency"] = extraction_concurrency
            preprocessing_metrics["raw_draft_count"] = raw_candidate_count
            preprocessing_metrics["duplicates_collapsed_safely_count"] = (
                json_metric_int(
                    cleanup_result.metrics, "exact_duplicate_candidate_collapse_count"
                )
            )
            preprocessing_metrics["source_refs_preserved_per_semantic_entry"] = True
            preprocessing_metrics["row_explosion_guard"] = (
                "raw_source_chunks_not_persisted_as_runtime_entries"
            )

            await repo.update_document_preprocessing_status(
                document_id,
                mode=mode,
                status=PREPROCESSING_STATUS_COMPLETED,
                model=result.model,
                prompt_version=result.prompt_version,
                metrics=preprocessing_metrics,
            )
            await repo.update_document_status(document_id, "processed")
            return KnowledgeDocumentProcessingResult(
                document_id=document_id,
                preprocessing_status=PREPROCESSING_STATUS_COMPLETED,
                structured_entries=len(canonical_entries),
            )
        except EmbeddingProviderError as exc:
            if exc.retryable:
                logger.warning(
                    "Knowledge embedding provider temporary failure during structured indexing",
                    extra={
                        "project_id": project_id,
                        "document_id": document_id,
                        "provider": exc.provider,
                        "task": exc.task,
                        "model": exc.model,
                        "error_type": type(exc).__name__,
                    },
                )
                raise

            logger.warning(
                "Knowledge embedding provider permanent failure during structured indexing",
                extra={
                    "project_id": project_id,
                    "document_id": document_id,
                    "provider": exc.provider,
                    "task": exc.task,
                    "model": exc.model,
                    "error_type": type(exc).__name__,
                },
            )
            await repo.update_document_status(document_id, "error", exc.detail)
            raise
        except KnowledgeDocumentDeletedDuringProcessingError as exc:
            logger.warning(
                "Knowledge document disappeared during structured indexing",
                extra={
                    "project_id": project_id,
                    "document_id": document_id,
                    "mode": mode,
                    "error_type": type(exc).__name__,
                },
            )
            raise
        except Exception as exc:
            error_message = str(exc)[:500] or type(exc).__name__
            logger.warning(
                "Knowledge preprocessing failed; structured pipeline stopped",
                extra={
                    "project_id": project_id,
                    "document_id": document_id,
                    "mode": mode,
                    "error_type": type(exc).__name__,
                    "error": error_message,
                    "fallback": "disabled",
                },
            )
            await repo.update_document_preprocessing_status(
                document_id,
                mode=mode,
                status=PREPROCESSING_STATUS_FAILED,
                error=error_message,
                model=active_model or None,
                prompt_version=active_prompt_version,
                metrics={
                    "answer_compiler": KCD_STAGE_K_COMPILER_VERSION,
                    "stage": "failed",
                    "status_message": build_preprocessing_failure_status_message(exc),
                    "error_type": type(exc).__name__,
                    "fallback": "disabled",
                    "source_chunk_count": len(indexable_chunks),
                    "technical_compiler_total_count": len(technical_batches),
                    "technical_source_char_budget": (
                        KCD_STAGE_K_TECHNICAL_SOURCE_CHAR_BUDGET
                    ),
                },
            )
            await repo.update_document_status(document_id, "error", error_message)
            raise ValidationError(error_message) from exc
