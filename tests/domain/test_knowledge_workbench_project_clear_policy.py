from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.domain.project_plane.knowledge_workbench.documents import (
    KnowledgeDocumentStatus,
)
from src.domain.project_plane.knowledge_workbench.errors import DomainInvariantError
from src.domain.project_plane.knowledge_workbench.processing import (
    ProcessingRunStatus,
)
from src.domain.project_plane.knowledge_workbench.project_clear import (
    decide_workbench_project_clear_transition,
)


def _cleared_at() -> datetime:
    return datetime(2026, 5, 31, tzinfo=timezone.utc)


def test_project_clear_transition_deletes_documents_and_terminalizes_runs() -> None:
    transition = decide_workbench_project_clear_transition(
        project_id="project-1",
        cleared_at=_cleared_at(),
    )

    assert transition.project_id == "project-1"
    assert transition.cleared_at == _cleared_at()
    assert transition.document_status_after is KnowledgeDocumentStatus.DELETED
    assert transition.processing_run_status_after is ProcessingRunStatus.DELETED
    assert transition.pending_queue_jobs_should_be_removed is True
    assert transition.runtime_publications_should_be_removed is True


def test_project_clear_transition_rejects_empty_project_id() -> None:
    with pytest.raises(DomainInvariantError, match="project_id is required"):
        decide_workbench_project_clear_transition(
            project_id="",
            cleared_at=_cleared_at(),
        )
