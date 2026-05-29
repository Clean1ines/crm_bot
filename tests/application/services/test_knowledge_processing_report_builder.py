from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from src.application.services.knowledge_processing_report_builder import (
    build_knowledge_processing_report,
)
from src.domain.project_plane.knowledge_document_lifecycle import (
    PROCESSING_PAUSED_QUOTA_STATUS,
)

ROOT = Path(__file__).resolve().parents[3]
REPORT_BUILDER = (
    ROOT / "src/application/services/knowledge_processing_report_builder.py"
)


def test_processing_report_builder_exposes_retry_for_failed_batches() -> None:
    document = SimpleNamespace(
        status="error",
        preprocessing_status="failed",
        preprocessing_metrics={"canonical_entry_count": 0},
        structured_entries=0,
        chunk_count=3,
    )
    batches = (
        SimpleNamespace(
            status="completed",
            batch_count=2,
            tokens_input=10,
            tokens_output=5,
            tokens_total=15,
        ),
        SimpleNamespace(
            status="failed",
            batch_count=2,
            tokens_input=7,
            tokens_output=0,
            tokens_total=7,
        ),
    )
    candidate_summary = SimpleNamespace(
        raw_count=2,
        total_count=2,
        grounded_count=1,
        rejected_count=0,
    )

    report = build_knowledge_processing_report(
        document_id="doc-1",
        document=document,
        batches=batches,
        candidate_summary=candidate_summary,
    )

    assert report.recoverable is True
    assert report.metrics["batch_failed"] == 1
    assert report.metrics["tokens_total"] == 22
    assert [action.id for action in report.actions] == [
        "retry_failed_batches",
        "publish_ready",
    ]


def test_processing_report_builder_marks_answer_resolution_processing() -> None:
    document = SimpleNamespace(
        status="processing",
        preprocessing_status="processing",
        preprocessing_metrics={
            "stage": "answer_resolution",
            "answer_resolution": {
                "status": "processing",
                "suspect_case_count": 4,
                "processed_case_count": 2,
            },
        },
        structured_entries=0,
        chunk_count=5,
    )
    candidate_summary = SimpleNamespace(
        raw_count=5,
        total_count=5,
        grounded_count=5,
        rejected_count=0,
    )

    report = build_knowledge_processing_report(
        document_id="doc-2",
        document=document,
        batches=(),
        candidate_summary=candidate_summary,
    )

    assert report.title == "Разрешаем похожие ответы"
    assert report.steps[2].id == "answer_resolution"
    assert report.steps[2].status == "processing"
    assert report.steps[2].current == 2
    assert report.steps[2].total == 4
    assert [action.id for action in report.actions] == ["cancel", "publish_ready"]


def test_processing_report_builder_uses_lifecycle_resolver_for_decisions() -> None:
    source = REPORT_BUILDER.read_text(encoding="utf-8")

    assert "resolve_knowledge_document_lifecycle(" in source
    assert "lifecycle_decision.is_processing" in source
    assert "lifecycle_decision.is_recoverable" in source
    assert "lifecycle_decision.actions" in source
    assert "can_resume =" not in source
    assert "is_cancelled" not in source
    assert '"остановлено пользователем"' not in source
    assert '"knowledge document processing was cancelled"' not in source


def test_processing_report_builder_keeps_quota_pause_auto_recoverable() -> None:
    document = SimpleNamespace(
        status=PROCESSING_PAUSED_QUOTA_STATUS,
        preprocessing_status="failed",
        preprocessing_error="quota exhausted",
        preprocessing_metrics={"stage": PROCESSING_PAUSED_QUOTA_STATUS},
        structured_entries=0,
        chunk_count=3,
    )
    candidate_summary = SimpleNamespace(
        raw_count=0,
        total_count=0,
        grounded_count=0,
        rejected_count=0,
    )

    report = build_knowledge_processing_report(
        document_id="doc-quota",
        document=document,
        batches=(),
        candidate_summary=candidate_summary,
    )

    action_ids = [action.id for action in report.actions]
    assert report.recoverable is True
    assert "retry_later" in action_ids
    assert "resume_processing" not in action_ids
    assert "cancel" not in action_ids
