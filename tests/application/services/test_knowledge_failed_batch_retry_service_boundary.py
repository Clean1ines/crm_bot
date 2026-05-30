from __future__ import annotations

from pathlib import Path


def test_failed_batch_handler_uses_retry_service_directly() -> None:
    source = Path(
        "src/infrastructure/queue/handlers/knowledge_failed_batches.py"
    ).read_text(encoding="utf-8")

    assert "KnowledgeFailedBatchRetryService" in source
    assert "KnowledgeIngestionService" not in source
    assert (
        "Legacy knowledge failed-batches retry handler cannot process mode=faq"
        in source
    )
    assert (
        "except (KnowledgePreprocessingValidationError, ValidationError) as exc:"
        in source
    )
    assert "except EmbeddingProviderError as exc:" in source
    assert "raise TransientJobError(" in source


def test_failed_batch_retry_service_keeps_mode_faq_guard_and_core_flow() -> None:
    source = Path(
        "src/application/services/knowledge_failed_batch_retry_service.py"
    ).read_text(encoding="utf-8")

    assert "if mode == MODE_FAQ:" in source
    assert "Legacy knowledge ingestion retry path is forbidden for mode=faq" in source
    assert '"reason": "no_failed_batches"' in source
    assert (
        "Saved compiler batch index is outside reconstructed technical batch range"
        in source
    )
    assert "delete_raw_answer_candidates_for_batch" in source
    assert "add_answer_candidates" in source
    assert "_canonical_entries_from_raw_answer_candidates" in source
    assert "persist_stage_e_compiler_outputs" in source
    assert 'await repo.update_document_status(document_id, "processed")' in source
    assert '"Some compiler batches still failed after retry"' in source


def test_ingestion_keeps_only_failed_batch_retry_wrapper() -> None:
    source = Path("src/application/services/knowledge_ingestion_service.py").read_text(
        encoding="utf-8"
    )

    method_index = source.index("async def retry_failed_batches")
    next_method_index = source.index(
        "async def _process_document_faq_surface", method_index
    )
    method_slice = source[method_index:next_method_index]

    assert "KnowledgeFailedBatchRetryService" in method_slice
    assert (
        "return await KnowledgeFailedBatchRetryService(self.pool).retry_failed_batches"
        in (method_slice)
    )
    assert "_technical_chunk_batches_for_answer_compiler" not in method_slice
    assert "delete_raw_answer_candidates_for_batch" not in method_slice
