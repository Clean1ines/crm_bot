from __future__ import annotations

from types import SimpleNamespace

from src.application.services.knowledge_processing_report_builder import (
    build_knowledge_processing_report,
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
