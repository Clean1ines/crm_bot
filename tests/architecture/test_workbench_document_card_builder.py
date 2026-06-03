from __future__ import annotations

from pathlib import Path


BUILDER = Path("src/application/workbench/document_card_builder.py")


def test_document_card_builder_outputs_new_workbench_card_contract() -> None:
    source = BUILDER.read_text(encoding="utf-8")

    assert "WorkbenchDocumentCardView" in source
    assert "WorkbenchCardTimerView" in source
    assert "WorkbenchCardUsageView" in source
    assert "WorkbenchRecoveryView" in source
    assert "WorkbenchRegistrySummaryView" in source
    assert "WorkbenchSurfaceSummaryView" in source
    assert "WorkbenchRuntimeSummaryView" in source


def test_document_card_builder_includes_user_facing_i18n_messages_and_actions() -> None:
    source = BUILDER.read_text(encoding="utf-8")

    for marker in (
        "knowledge.workbench.card.status",
        "knowledge.workbench.card.messages",
        "knowledge.workbench.card.actions",
        "default_message",
        "default_label",
        "default_confirmation",
        "Открыть курацию",
        "Отменить автопродолжение",
        "Промежуточные данные очищены",
    ):
        assert marker in source


def test_document_card_builder_knows_processing_controls_and_recovery() -> None:
    source = BUILDER.read_text(encoding="utf-8")

    for marker in (
        "CANCEL_PROCESSING",
        "RESUME_PROCESSING",
        "CANCEL_SCHEDULED_RECOVERY",
        "DELETE_DOCUMENT",
        "OPEN_CURATION",
        "PUBLISH_READY",
        "OPEN_PUBLISHED_SURFACES",
    ):
        assert marker in source


def test_document_card_builder_does_not_depend_on_legacy_chunk_model() -> None:
    source = BUILDER.read_text(encoding="utf-8")

    forbidden = (
        "chunk_count",
        "structured_entries",
        "structured_chunk_count",
        "answer_drafts",
        "source_units",
        "KnowledgePreviewResultDto",
        "KnowledgeReadyAnswerPublicationService",
        "process_knowledge_upload",
        "knowledge_compilation",
    )
    for marker in forbidden:
        assert marker not in source


def test_document_card_builder_is_provider_agnostic() -> None:
    source = BUILDER.read_text(encoding="utf-8")

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
