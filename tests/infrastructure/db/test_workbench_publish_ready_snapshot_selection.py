from __future__ import annotations

from dataclasses import dataclass

import pytest

from src.infrastructure.db.knowledge_workbench_repository import (
    KnowledgeWorkbenchRepository,
)


@dataclass(slots=True)
class FakeRow:
    values: dict[str, object]

    def __getitem__(self, key: str) -> object:
        return self.values[key]


@dataclass(slots=True)
class NoopTransaction:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(
        self,
        exc_type: object,
        exc: object,
        traceback: object,
    ) -> None:
        return None


@dataclass(slots=True)
class CapturingConnection:
    first_row: FakeRow | None
    second_row: FakeRow | None
    fetchrow_queries: list[str]
    execute_queries: list[str]

    async def fetchrow(self, query: str, *args: object) -> FakeRow | None:
        del args
        self.fetchrow_queries.append(" ".join(query.lower().split()))
        if len(self.fetchrow_queries) == 1:
            return self.first_row
        return self.second_row

    async def execute(self, query: str, *args: object) -> str:
        del args
        self.execute_queries.append(" ".join(query.lower().split()))
        return "UPDATE 1"

    def transaction(self) -> NoopTransaction:
        return NoopTransaction()


@pytest.mark.asyncio
async def test_publish_ready_selects_snapshot_from_canonicalization_barrier_marker() -> None:
    connection = CapturingConnection(
        first_row=None,
        second_row=FakeRow(
            {
                "snapshot_id": "snapshot-final",
                "processing_run_id": "run-1",
            }
        ),
        fetchrow_queries=[],
        execute_queries=[],
    )
    repository = KnowledgeWorkbenchRepository(connection)

    snapshot_id = await repository.publish_latest_reconciled_fact_registry_snapshot(
        project_id="00000000-0000-0000-0000-000000000001",
        document_id="document-1",
    )

    assert snapshot_id == "snapshot-final"

    selection_query = connection.fetchrow_queries[1]
    assert "fact_registry_canonicalization_barrier" in selection_query
    assert "final_snapshot_id" in selection_query
    assert "snapshot.entries_payload ->> 'contract' = 'fact_registry'" in selection_query
    assert "snapshot.entry_count > 0" in selection_query
    assert "run.status = 'completed'" in selection_query

    assert "faq_surface_final_reconciliation" not in selection_query
    assert "faq_surface_registry_merge" not in selection_query

    assert any("set is_final_published = true" in query for query in connection.execute_queries)


@pytest.mark.asyncio
async def test_publish_ready_returns_existing_published_snapshot_without_reselecting() -> None:
    connection = CapturingConnection(
        first_row=FakeRow({"snapshot_id": "already-published"}),
        second_row=None,
        fetchrow_queries=[],
        execute_queries=[],
    )
    repository = KnowledgeWorkbenchRepository(connection)

    snapshot_id = await repository.publish_latest_reconciled_fact_registry_snapshot(
        project_id="00000000-0000-0000-0000-000000000001",
        document_id="document-1",
    )

    assert snapshot_id == "already-published"
    assert len(connection.fetchrow_queries) == 1
    assert connection.execute_queries == []
