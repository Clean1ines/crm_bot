from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.domain.project_plane.knowledge_workbench.documents import (
    KnowledgeDocumentStatus,
)
from src.domain.project_plane.knowledge_workbench.processing import ProcessingRunStatus
from src.infrastructure.db.knowledge_workbench_repository import (
    KnowledgeWorkbenchRepository,
)


class FakeConnection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    async def execute(self, query: str, *args: object) -> str:
        self.calls.append((query, args))
        return "UPDATE 1"

    def transaction(self) -> object:
        return self

    async def __aenter__(self) -> None:
        return None

    async def __aexit__(
        self,
        exc_type: object,
        exc: object,
        traceback: object,
    ) -> None:
        return None


@pytest.mark.asyncio
async def test_persist_document_delete_transition_marks_document_run_and_workbench_queues() -> (
    None
):
    connection = FakeConnection()
    repository = KnowledgeWorkbenchRepository(connection)
    deleted_at = datetime(2026, 6, 5, 12, 0, tzinfo=timezone.utc)

    await repository.persist_document_delete_transition(
        project_id="0f36f58c-fc0d-4741-bff0-9de6e330ebe1",
        document_id="document-1",
        current_processing_run_id="run-1",
        document_status=KnowledgeDocumentStatus.DELETED,
        processing_run_status=ProcessingRunStatus.DELETED,
        deleted_at=deleted_at,
    )

    sql = "\\n".join(query for query, _ in connection.calls)

    assert "UPDATE knowledge_workbench_documents" in sql
    assert "current_processing_run_id = NULL" in sql
    assert "deleted_at = $4" in sql
    assert "UPDATE knowledge_workbench_document_sections" in sql
    assert "UPDATE knowledge_workbench_section_batch_queue_items" in sql
    assert "UPDATE knowledge_workbench_fact_registry_application_queue" in sql
    assert "UPDATE knowledge_workbench_processing_runs" in sql
    assert "document_deleted" in sql

    assert "UPDATE execution_queue" not in sql
    assert "locked_by" not in sql
    assert "locked_at" not in sql


@pytest.mark.asyncio
async def test_persist_document_delete_transition_allows_document_without_run() -> None:
    connection = FakeConnection()
    repository = KnowledgeWorkbenchRepository(connection)

    await repository.persist_document_delete_transition(
        project_id="0f36f58c-fc0d-4741-bff0-9de6e330ebe1",
        document_id="document-1",
        current_processing_run_id=None,
        document_status=KnowledgeDocumentStatus.DELETED,
        processing_run_status=None,
        deleted_at=datetime(2026, 6, 5, 12, 0, tzinfo=timezone.utc),
    )

    sql = "\\n".join(query for query, _ in connection.calls)

    assert "UPDATE knowledge_workbench_documents" in sql
    assert "UPDATE knowledge_workbench_processing_runs" not in sql
    assert "UPDATE execution_queue" not in sql
