from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, cast

import pytest

from src.infrastructure.db.knowledge_workbench_repository import (
    KnowledgeWorkbenchRepository,
)


def _workbench_repository(connection: object) -> KnowledgeWorkbenchRepository:
    factory = cast(
        Callable[[object], KnowledgeWorkbenchRepository],
        KnowledgeWorkbenchRepository,
    )
    return factory(connection)


@dataclass(slots=True)
class FakeTransaction:
    entered: int = 0
    exited: int = 0

    async def __aenter__(self) -> None:
        self.entered += 1
        return None

    async def __aexit__(self, exc_type, exc, tb) -> None:
        self.exited += 1
        return None


@dataclass(slots=True)
class FakeConnection:
    transaction_obj: FakeTransaction = field(default_factory=FakeTransaction)
    executed: list[tuple[str, tuple[object, ...]]] = field(default_factory=list)

    def transaction(self) -> FakeTransaction:
        return self.transaction_obj

    async def execute(self, query: str, *args: object) -> str:
        self.executed.append((query, args))
        return "UPDATE 1"

    async def fetchrow(self, query: str, *args: object):
        raise AssertionError("fetchrow must not be used")

    async def fetch(self, query: str, *args: object):
        raise AssertionError("fetch must not be used")


@pytest.mark.asyncio
async def test_mark_parallel_processing_completed_updates_document_and_run_terminal_success() -> (
    None
):
    connection = FakeConnection()
    repository = _workbench_repository(connection)

    await repository.mark_parallel_processing_completed(
        project_id="project-1",
        document_id="document-1",
        processing_run_id="processing-run-1",
    )

    assert connection.transaction_obj.entered == 1
    assert connection.transaction_obj.exited == 1
    assert len(connection.executed) == 2

    document_query, document_args = connection.executed[0]
    run_query, run_args = connection.executed[1]

    normalized_document_query = " ".join(document_query.lower().split())
    normalized_run_query = " ".join(run_query.lower().split())

    assert "update knowledge_workbench_documents" in normalized_document_query
    assert "set status = 'processed'" in normalized_document_query
    assert "last_error_kind = null" in normalized_document_query
    assert "current_processing_run_id = $3" in normalized_document_query
    assert "status not in ('deleted', 'cancelled')" in normalized_document_query

    assert "update knowledge_workbench_processing_runs" in normalized_run_query
    assert "set status = 'completed'" in normalized_run_query
    assert "resume_policy = 'forbidden'" in normalized_run_query
    assert "completed_at = coalesce(completed_at, now())" in normalized_run_query
    assert "stopped_at = coalesce(stopped_at, now())" in normalized_run_query
    assert "last_error_kind = null" in normalized_run_query
    assert "deleted_at is null" in normalized_run_query
    assert "failed_fatal" in normalized_run_query

    assert document_args == ("project-1", "document-1", "processing-run-1")
    assert run_args == ("project-1", "document-1", "processing-run-1")
