from __future__ import annotations

from dataclasses import dataclass

from src.application.services.knowledge_processing_report_builder import (
    build_knowledge_processing_report,
)
from src.domain.project_plane.knowledge_document_lifecycle import (
    LEGACY_USER_CANCELLED_MESSAGE,
    PROCESSING_PAUSED_QUOTA_STATUS,
)


@dataclass(slots=True)
class Document:
    status: str
    preprocessing_status: str | None
    preprocessing_error: str | None
    preprocessing_metrics: dict[str, object] | None
    structured_entries: int | None = 0
    chunk_count: int = 1


@dataclass(slots=True)
class CandidateSummary:
    raw_count: int = 0
    total_count: int = 0
    grounded_count: int = 0
    rejected_count: int = 0


def _actions_by_id(document: Document):
    report = build_knowledge_processing_report(
        document_id="document-1",
        document=document,
        batches=(),
        candidate_summary=CandidateSummary(),
    )
    return {action.id: action for action in report.actions}


def _action_ids(document: Document) -> set[str]:
    return set(_actions_by_id(document))


def test_report_resume_action_is_lifecycle_driven_for_manual_cancel() -> None:
    actions = _action_ids(
        Document(
            status="error",
            preprocessing_status="failed",
            preprocessing_error=LEGACY_USER_CANCELLED_MESSAGE,
            preprocessing_metrics={},
        )
    )

    assert "resume_processing" in actions
    assert "retry_later" not in actions


def test_report_does_not_show_manual_resume_for_quota_pause() -> None:
    actions = _action_ids(
        Document(
            status=PROCESSING_PAUSED_QUOTA_STATUS,
            preprocessing_status=PROCESSING_PAUSED_QUOTA_STATUS,
            preprocessing_error=None,
            preprocessing_metrics={"stage": PROCESSING_PAUSED_QUOTA_STATUS},
        )
    )

    assert "resume_processing" not in actions
    assert "retry_later" in actions


def test_manual_cancel_resume_processing_action_is_primary() -> None:
    actions = _actions_by_id(
        Document(
            status="error",
            preprocessing_status="failed",
            preprocessing_error=LEGACY_USER_CANCELLED_MESSAGE,
            preprocessing_metrics={},
        )
    )

    assert actions["resume_processing"].kind == "primary"
    assert actions["resume_processing"].enabled is True
    assert actions["resume_processing"].label == "Продолжить обработку"
