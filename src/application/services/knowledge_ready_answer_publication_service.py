from __future__ import annotations

from src.application.errors import ValidationError
from src.application.ports.knowledge.ready_answer_publication import (
    KnowledgeReadyAnswerPublicationRepositoryFactoryPort,
)
from src.application.services.knowledge_canonical_publication_builder import (
    canonical_entries_from_raw_answer_candidates as _canonical_entries_from_raw_answer_candidates,
)
from src.application.ports.logger_port import LoggerPort
from src.application.services.knowledge_stage_e_publication_helpers import (
    _persist_stage_e_compiler_outputs,
)
from src.domain.project_plane.json_types import JsonObject
from src.domain.project_plane.knowledge_preprocessing import (
    MODE_FAQ,
    KnowledgePreprocessingValidationError,
    normalize_preprocessing_mode,
    PREPROCESSING_STATUS_COMPLETED,
    PREPROCESSING_STATUS_PROCESSING,
)


class KnowledgeReadyAnswerPublicationService:
    def __init__(self, pool: object) -> None:
        self.pool = pool

    async def publish_ready_answers(
        self,
        *,
        project_id: str,
        document_id: str,
        knowledge_repo_factory: KnowledgeReadyAnswerPublicationRepositoryFactoryPort,
        logger: LoggerPort,
    ) -> JsonObject:
        repo = knowledge_repo_factory(self.pool)
        document = await repo.get_document(document_id)
        if document is None or document.project_id != project_id:
            raise ValidationError("Knowledge document not found")

        mode = normalize_preprocessing_mode(document.preprocessing_mode)
        if mode == MODE_FAQ:
            raise KnowledgePreprocessingValidationError(
                "Legacy knowledge ingestion preprocessor path is forbidden for mode=faq. "
                "Use Retrieval Surface Compilation pipeline."
            )
        if document.status in {"pending", "processing"} or (
            document.preprocessing_status == PREPROCESSING_STATUS_PROCESSING
        ):
            raise ValidationError(
                "Knowledge document is still processing; wait before publishing drafts"
            )

        source_chunks = await repo.list_document_source_chunks(
            project_id=project_id,
            document_id=document_id,
        )
        if not source_chunks:
            raise ValidationError("Knowledge document has no saved source chunks")

        runtime_entries = await repo.list_document_runtime_entries(
            project_id=project_id,
            document_id=document_id,
        )

        raw_candidates = await repo.list_document_raw_answer_candidates(
            project_id=project_id,
            document_id=document_id,
        )
        if not raw_candidates and not runtime_entries:
            raise ValidationError("Knowledge document has no ready answer drafts")

        batches = await repo.list_document_compiler_batches(
            project_id=project_id,
            document_id=document_id,
        )
        batch_failed = sum(1 for batch in batches if batch.status == "failed")
        batch_completed = sum(1 for batch in batches if batch.status == "completed")
        all_batches_completed = bool(batches) and all(
            batch.status == "completed" for batch in batches
        )
        compiler_run_id = (
            runtime_entries[0].compiler_run_id
            if runtime_entries
            else raw_candidates[0].compiler_run_id
        )

        canonical_entries = (
            runtime_entries
            if runtime_entries
            else _canonical_entries_from_raw_answer_candidates(
                project_id=project_id,
                document_id=document_id,
                compiler_run_id=compiler_run_id,
                mode=mode,
                candidates=raw_candidates,
            )
        )
        if not canonical_entries:
            raise ValidationError("Knowledge document has no publishable answer drafts")

        await _persist_stage_e_compiler_outputs(
            repo=repo,
            project_id=project_id,
            document_id=document_id,
            compiler_run_id=compiler_run_id,
            source_chunks=source_chunks,
            entries=canonical_entries,
            complete_run=all_batches_completed,
        )

        metrics: JsonObject = {
            "stage": "publish_ready",
            "status_message": (
                "Готовые ответы опубликованы; проблемные части можно повторить"
                if batch_failed > 0
                else "Готовые ответы опубликованы в базу знаний"
            ),
            "raw_answer_count": len(raw_candidates),
            "published_answer_count": len(canonical_entries),
            "canonical_entry_count": len(canonical_entries),
            "batch_completed": batch_completed,
            "batch_failed": batch_failed,
            "partial_publish": batch_failed > 0,
        }
        await repo.update_document_preprocessing_status(
            document_id,
            mode=mode,
            status=PREPROCESSING_STATUS_COMPLETED,
            model=document.preprocessing_model,
            prompt_version=document.preprocessing_prompt_version,
            metrics=metrics,
        )
        await repo.update_document_status(document_id, "processed")

        logger.info(
            "Knowledge ready answer drafts published",
            extra={
                "project_id": project_id,
                "document_id": document_id,
                "published_answer_count": len(canonical_entries),
                "batch_failed": batch_failed,
            },
        )
        return {
            "status": "completed" if batch_failed == 0 else "partial",
            "document_id": document_id,
            "published_answer_count": len(canonical_entries),
            "raw_answer_count": len(raw_candidates),
            "remaining_failed_batch_count": batch_failed,
        }
