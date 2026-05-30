from __future__ import annotations

from pathlib import Path


def test_publish_ready_handler_uses_ready_publication_service_directly() -> None:
    source = Path(
        "src/infrastructure/queue/handlers/knowledge_publish_ready.py"
    ).read_text(encoding="utf-8")

    assert "KnowledgeReadyAnswerPublicationService" in source
    assert "KnowledgeIngestionService" not in source
    assert "Legacy knowledge publish-ready handler cannot process mode=faq" in source
    assert (
        "except (KnowledgePreprocessingValidationError, ValidationError) as exc:"
        in source
    )
    assert "except EmbeddingProviderError as exc:" in source
    assert "raise TransientJobError(" in source


def test_ready_publication_service_preserves_metrics_and_builder_usage() -> None:
    source = Path(
        "src/application/services/knowledge_ready_answer_publication_service.py"
    ).read_text(encoding="utf-8")

    assert "knowledge_canonical_publication_builder" in source
    assert "canonical_entries_from_raw_answer_candidates" in source
    assert "if mode == MODE_FAQ:" in source
    assert (
        "Legacy knowledge ingestion preprocessor path is forbidden for mode=faq"
        in source
    )

    for marker in (
        '"stage": "publish_ready"',
        '"status_message"',
        '"raw_answer_count"',
        '"published_answer_count"',
        '"canonical_entry_count"',
        '"batch_completed"',
        '"batch_failed"',
        '"partial_publish"',
    ):
        assert marker in source

    assert "persist_stage_e_compiler_outputs" in source
    assert "complete_run=all_batches_completed" in source
    assert 'await repo.update_document_status(document_id, "processed")' in source


def test_ingestion_keeps_only_publish_ready_wrapper() -> None:
    source = Path("src/application/services/knowledge_ingestion_service.py").read_text(
        encoding="utf-8"
    )

    method_index = source.index("async def publish_ready_answers")
    next_method_index = source.index("async def retry_failed_batches", method_index)
    method_slice = source[method_index:next_method_index]
    compact_method_slice = "".join(method_slice.split())

    assert "KnowledgeReadyAnswerPublicationService" in method_slice
    assert (
        "returnawaitKnowledgeReadyAnswerPublicationService(self.pool).publish_ready_answers"
        in compact_method_slice
    )
    assert "_canonical_entries_from_raw_answer_candidates" not in method_slice
    assert "persist_stage_e_compiler_outputs" not in method_slice
    assert '"published_answer_count"' not in method_slice
    assert '"partial_publish"' not in method_slice
