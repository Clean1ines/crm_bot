from __future__ import annotations

from pathlib import Path


CONTRACT = Path("src/application/workbench/document_card_contract.py")


def test_document_card_contract_models_new_workbench_vertical_not_legacy_chunks() -> (
    None
):
    source = CONTRACT.read_text(encoding="utf-8")

    required = (
        "WorkbenchDocumentLifecycleState",
        "WorkbenchCardTimerView",
        "WorkbenchCardUsageView",
        "WorkbenchRecoveryView",
        "WorkbenchRegistrySummaryView",
        "WorkbenchSurfaceSummaryView",
        "WorkbenchRuntimeSummaryView",
        "WorkbenchCardUserMessage",
        "WorkbenchCardErrorView",
        "OPEN_CURATION",
        "CANCEL_SCHEDULED_RECOVERY",
        "TRANSIENT_PURGED",
    )
    for marker in required:
        assert marker in source

    forbidden = (
        "chunk_count",
        "structured_entries",
        "structured_chunk_count",
        "answer_drafts",
        "source_units",
        "KnowledgePreviewResultDto",
        "KnowledgeReadyAnswerPublicationService",
    )
    for marker in forbidden:
        assert marker not in source


def test_document_card_contract_is_provider_agnostic_and_not_groq_specific() -> None:
    source = CONTRACT.read_text(encoding="utf-8")

    forbidden = (
        "Groq",
        "AsyncGroq",
        "GROQ_API_KEY",
        "RotatingAsyncGroq",
        "GroqLlmJsonInvocationAdapter",
        "api_key",
    )
    for marker in forbidden:
        assert marker not in source


def test_document_card_contract_uses_i18n_keys_and_user_messages() -> None:
    source = CONTRACT.read_text(encoding="utf-8")

    assert "i18n_key" in source
    assert "default_message" in source
    assert "default_label" in source
    assert "default_confirmation" in source
    assert "internal_error_ref" in source
    assert "debug_ref" in source


def test_document_card_contract_has_controls_for_processing_recovery_and_curation() -> (
    None
):
    source = CONTRACT.read_text(encoding="utf-8")

    for marker in (
        "CANCEL_PROCESSING",
        "RESUME_PROCESSING",
        "CANCEL_SCHEDULED_RECOVERY",
        "DELETE_DOCUMENT",
        "OPEN_CURATION",
        "PUBLISH_READY",
        "OPEN_PUBLISHED_SURFACES",
        "REPROCESS_FRESH",
    ):
        assert marker in source


def test_document_card_contract_makes_published_workspace_cleaning_explicit() -> None:
    source = CONTRACT.read_text(encoding="utf-8")

    assert "PUBLISHED_WORKSPACE_CLEANED" in source
    assert "RESUME_FORBIDDEN_AFTER_PUBLICATION" in source
    assert "resume must be unavailable after transient purge" in source
    assert "resume action must not be enabled after transient purge" in source
