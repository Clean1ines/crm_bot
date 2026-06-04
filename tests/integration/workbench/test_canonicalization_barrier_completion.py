from __future__ import annotations

from dataclasses import dataclass
import pytest

from src.infrastructure.db.knowledge_workbench_repository import (
    KnowledgeWorkbenchRepository,
)


@dataclass(slots=True)
class FakeRow:
    completed: bool

    def __getitem__(self, key: str) -> object:
        if key == "completed":
            return self.completed
        raise KeyError(key)


@dataclass(slots=True)
class CapturingConnection:
    completed: bool
    query: str = ""
    args: tuple[object, ...] = ()

    async def fetchrow(self, query: str, *args: object) -> FakeRow:
        self.query = query
        self.args = args
        return FakeRow(self.completed)


@pytest.mark.asyncio
async def test_completed_unit_artifact_without_barrier_marker_is_not_completion() -> (
    None
):
    connection = CapturingConnection(completed=False)
    repository: KnowledgeWorkbenchRepository = KnowledgeWorkbenchRepository(connection)

    completed = await repository.has_completed_fact_registry_canonicalization(
        project_id="00000000-0000-0000-0000-000000000001",
        document_id="document-1",
        processing_run_id="processing-run-1",
    )

    assert completed is False
    assert "fact_registry_canonicalization_barrier" in connection.query
    assert "fact_registry_canonicalization'" not in connection.query
    assert "faq_surface_registry_merge" not in connection.query
    assert "knowledge_workbench_registry_snapshots" in connection.query
    assert (
        "snapshot.entries_payload ->> 'contract' = 'fact_registry'" in connection.query
    )
    assert "snapshot.entry_count >= 0" in connection.query


@pytest.mark.asyncio
async def test_completed_barrier_marker_with_final_snapshot_is_completion() -> None:
    connection = CapturingConnection(completed=True)
    repository: KnowledgeWorkbenchRepository = KnowledgeWorkbenchRepository(connection)

    completed = await repository.has_completed_fact_registry_canonicalization(
        project_id="00000000-0000-0000-0000-000000000001",
        document_id="document-1",
        processing_run_id="processing-run-1",
    )

    assert completed is True
    assert connection.args == (
        "00000000-0000-0000-0000-000000000001",
        "document-1",
        "processing-run-1",
    )
