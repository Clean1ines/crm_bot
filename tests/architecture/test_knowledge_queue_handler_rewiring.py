from __future__ import annotations

from pathlib import Path


HANDLERS = {
    "upload": Path("src/infrastructure/queue/handlers/knowledge_upload.py"),
    "publish_ready": Path(
        "src/infrastructure/queue/handlers/knowledge_publish_ready.py"
    ),
    "failed_batches": Path(
        "src/infrastructure/queue/handlers/knowledge_failed_batches.py"
    ),
    "retighten": Path("src/infrastructure/queue/handlers/knowledge_retighten.py"),
}


def test_upload_handler_routes_faq_and_structured_ingestion_directly() -> None:
    source = HANDLERS["upload"].read_text(encoding="utf-8")

    assert "KnowledgeFaqSurfaceIngestionService" in source
    assert "KnowledgeStructuredIngestionService" in source
    assert "KnowledgeIngestionService" not in source

    faq_branch = source.split("if mode == MODE_FAQ:", 1)[1].split(
        "await KnowledgeStructuredIngestionService", 1
    )[0]
    assert "KnowledgeFaqSurfaceIngestionService" in faq_branch
    assert (
        "lifecycle_trigger=_knowledge_upload_lifecycle_trigger(dto.source)"
        in faq_branch
    )
    assert "resume_run_id=dto.resume_run_id" in faq_branch


def test_legacy_non_upload_handlers_use_extracted_services_directly() -> None:
    expectations = {
        "publish_ready": "KnowledgeReadyAnswerPublicationService",
        "failed_batches": "KnowledgeFailedBatchRetryService",
        "retighten": "KnowledgeRetightenService",
    }

    for name, service_name in expectations.items():
        source = HANDLERS[name].read_text(encoding="utf-8")

        assert service_name in source
        assert "KnowledgeIngestionService" not in source
        assert (
            "from src.application.services.knowledge_ingestion_service import"
            not in source
        )


def test_legacy_non_upload_handlers_preserve_mode_faq_guards() -> None:
    expected_messages = {
        "publish_ready": "Legacy knowledge publish-ready handler cannot process mode=faq",
        "failed_batches": "Legacy knowledge failed-batches retry handler cannot process mode=faq",
        "retighten": "Legacy knowledge retighten handler cannot process mode=faq",
    }

    for name, message in expected_messages.items():
        source = HANDLERS[name].read_text(encoding="utf-8")

        assert "preprocessing_mode == MODE_FAQ" in source
        assert message in source
        assert "raise PermanentJobError(" in source


def test_handler_error_mapping_is_unchanged() -> None:
    for name, path in HANDLERS.items():
        source = path.read_text(encoding="utf-8")

        assert (
            "except (KnowledgePreprocessingValidationError, ValidationError) as exc:"
            in source
        )
        assert "except EmbeddingProviderError as exc:" in source
        assert "raise TransientJobError(" in source
        assert "raise PermanentJobError(exc.detail) from exc" in source

    upload_source = HANDLERS["upload"].read_text(encoding="utf-8")
    assert (
        "except KnowledgeDocumentDeletedDuringProcessingError as exc:" in upload_source
    )
    assert "raise PermanentJobError(str(exc)) from exc" in upload_source
