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
    execute_results: list[str]
    execute_calls: list[tuple[str, tuple[object, ...]]] = field(default_factory=list)

    def transaction(self) -> NoopTransaction:
        return NoopTransaction()

    async def execute(self, query: str, *args: object) -> str:
        self.execute_calls.append((" ".join(query.lower().split()), args))
        if self.execute_results:
            return self.execute_results.pop(0)
        return "DELETE 0"

    async def fetchrow(
        self,
        query: str,
        *args: object,
    ) -> Mapping[str, object] | None:
        raise AssertionError(f"unexpected fetchrow: {query} {args}")

    async def fetch(
        self,
        query: str,
        *args: object,
    ) -> Sequence[Mapping[str, object]]:
        raise AssertionError(f"unexpected fetch: {query} {args}")


@pytest.mark.asyncio
async def test_cleanup_document_final_retrieval_projections_deletes_all_document_runtime_vectors() -> (
    None
):
    connection = CapturingConnection(
        execute_results=["DELETE 1", "DELETE 2", "DELETE 3", "DELETE 4"]
    )
    repository = KnowledgeWorkbenchRepository(connection)

    count = await repository.cleanup_document_final_retrieval_projections(
        project_id="00000000-0000-0000-0000-000000000001",
        document_id="document-1",
    )

    assert count == 10
    joined_sql = "\\n".join(query for query, _args in connection.execute_calls)

    assert "delete from knowledge_workbench_runtime_retrieval_entries" in joined_sql
    assert "delete from knowledge_workbench_local_claim_retrieval_entries" in joined_sql
    assert "delete from knowledge_retrieval_surface" in joined_sql
    assert "delete from knowledge_entries" in joined_sql
    assert "entry_kind = 'faq_workbench_fact'" in joined_sql
    assert "metadata ->> 'workbench_document_id' = $2" in joined_sql
    assert "knowledge_workbench_canonical_facts" in joined_sql

    assert connection.execute_calls[0][1] == (
        "00000000-0000-0000-0000-000000000001",
        "document-1",
    )


@pytest.mark.asyncio
async def test_cleanup_project_final_retrieval_projections_deletes_all_project_runtime_vectors() -> (
    None
):
    connection = CapturingConnection(
        execute_results=["DELETE 5", "DELETE 6", "DELETE 7", "DELETE 8"]
    )
    repository = KnowledgeWorkbenchRepository(connection)

    count = await repository.cleanup_project_final_retrieval_projections(
        project_id="00000000-0000-0000-0000-000000000001",
    )

    assert count == 26
    joined_sql = "\\n".join(query for query, _args in connection.execute_calls)

    assert "delete from knowledge_workbench_runtime_retrieval_entries" in joined_sql
    assert "delete from knowledge_workbench_local_claim_retrieval_entries" in joined_sql
    assert "delete from knowledge_retrieval_surface" in joined_sql
    assert "delete from knowledge_entries" in joined_sql
    assert "entry_kind = 'faq_workbench_fact'" in joined_sql

    assert all(
        args == ("00000000-0000-0000-0000-000000000001",)
        for _query, args in connection.execute_calls
    )
