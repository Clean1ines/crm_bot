from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from src.domain.project_plane.knowledge_workbench.deletion import (
    decide_workbench_document_delete_transition,
)
from src.domain.project_plane.knowledge_workbench.documents import (
    KnowledgeDocumentStatus,
)
from src.domain.project_plane.knowledge_workbench.errors import DomainInvariantError
from src.domain.project_plane.knowledge_workbench.processing import (
    ProcessingRunStatus,
)


@dataclass(frozen=True, slots=True)
class FakeDocument:
    project_id: str = "project-1"
    document_id: str = "document-1"
    status: KnowledgeDocumentStatus = KnowledgeDocumentStatus.PROCESSING
    current_processing_run_id: str | None = "processing-run-1"


@dataclass(frozen=True, slots=True)
class FakeRun:
    project_id: str = "project-1"
    document_id: str = "document-1"
    processing_run_id: str = "processing-run-1"
    status: ProcessingRunStatus = ProcessingRunStatus.RUNNING


def _deleted_at() -> datetime:
    return datetime(2026, 5, 31, tzinfo=timezone.utc)


def test_delete_transition_marks_document_deleted_and_terminalizes_current_run() -> (
    None
):
    transition = decide_workbench_document_delete_transition(
        document=FakeDocument(),
        current_processing_run=FakeRun(status=ProcessingRunStatus.PAUSED_QUOTA),
        deleted_at=_deleted_at(),
    )

    assert transition.document_status_after is KnowledgeDocumentStatus.DELETED
    assert transition.processing_run_status_after is ProcessingRunStatus.DELETED
    assert transition.processing_run_id == "processing-run-1"
    assert transition.pending_queue_jobs_should_be_removed is True
    assert transition.runtime_publication_should_be_removed is True


def test_delete_transition_allows_processed_document_without_current_run() -> None:
    transition = decide_workbench_document_delete_transition(
        document=FakeDocument(
            status=KnowledgeDocumentStatus.PROCESSED,
            current_processing_run_id=None,
        ),
        current_processing_run=None,
        deleted_at=_deleted_at(),
    )

    assert transition.document_status_after is KnowledgeDocumentStatus.DELETED
    assert transition.processing_run_id is None
    assert transition.processing_run_status_after is None


def test_delete_transition_rejects_already_deleted_document() -> None:
    with pytest.raises(DomainInvariantError, match="already deleted"):
        decide_workbench_document_delete_transition(
            document=FakeDocument(status=KnowledgeDocumentStatus.DELETED),
            current_processing_run=FakeRun(),
            deleted_at=_deleted_at(),
        )


def test_delete_transition_rejects_wrong_current_run_document_pair() -> None:
    with pytest.raises(DomainInvariantError, match="document_id mismatch"):
        decide_workbench_document_delete_transition(
            document=FakeDocument(),
            current_processing_run=FakeRun(document_id="other-document"),
            deleted_at=_deleted_at(),
        )
