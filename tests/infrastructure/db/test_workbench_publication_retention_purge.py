from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

import pytest

from src.infrastructure.db.knowledge_workbench_repository import (
    KnowledgeWorkbenchRepository,
)


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
    execute_calls: list[tuple[str, tuple[object, ...]]] = field(default_factory=list)

    def transaction(self) -> NoopTransaction:
        return NoopTransaction()

    async def execute(self, query: str, *args: object) -> str:
        self.execute_calls.append((" ".join(query.lower().split()), args))
        return "OK"

    async def fetchrow(
        self,
        query: str,
        *args: object,
    ) -> Mapping[str, object] | None:
        raise AssertionError(f"unexpected fetchrow call: {query} {args}")

    async def fetch(
        self,
        query: str,
        *args: object,
    ) -> Sequence[Mapping[str, object]]:
        raise AssertionError(f"unexpected fetch call: {query} {args}")


@pytest.mark.asyncio
async def test_publication_purge_removes_transient_retrieval_projections_but_not_production_vectors() -> (
    None
):
    connection = CapturingConnection()
    repository = KnowledgeWorkbenchRepository(connection)

    await repository.purge_transient_processing_workspace_after_publication(
        project_id="00000000-0000-0000-0000-000000000001",
        document_id="document-1",
        processing_run_id="run-1",
    )

    joined_sql = "\\n".join(query for query, _args in connection.execute_calls)

    assert "delete from execution_queue" in joined_sql
    assert "delete from knowledge_workbench_local_claim_retrieval_entries" in joined_sql
    assert "delete from knowledge_workbench_runtime_retrieval_entries" in joined_sql
    assert "delete from knowledge_workbench_registry_snapshots" in joined_sql
    assert "delete from knowledge_workbench_processing_runs" in joined_sql
    assert "update knowledge_workbench_documents" in joined_sql
    assert "retention_state = 'transient_purged'" in joined_sql

    assert "delete from knowledge_retrieval_surface" not in joined_sql
    assert "delete from knowledge_entries" not in joined_sql
    assert "entry_kind = 'faq_workbench_fact'" not in joined_sql

    local_claim_delete = next(
        query
        for query, _args in connection.execute_calls
        if "delete from knowledge_workbench_local_claim_retrieval_entries" in query
    )
    assert "processing_run_id = $3" in local_claim_delete

    debug_runtime_delete = next(
        query
        for query, _args in connection.execute_calls
        if "delete from knowledge_workbench_runtime_retrieval_entries" in query
    )
    assert "knowledge_workbench_canonical_facts" in debug_runtime_delete
    assert "fact.document_id = $2" in debug_runtime_delete
