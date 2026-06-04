from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from src.application.services.faq_workbench_retrieval_surface_publication_service import (
    WorkbenchRetrievalSurfaceEntry,
)
from src.infrastructure.db.workbench_retrieval_surface_repository import (
    WorkbenchRetrievalSurfaceRepository,
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

    async def fetchval(self, query: str, *args: object) -> object:
        raise AssertionError(f"unexpected fetchval: {query} {args}")


def _entry() -> WorkbenchRetrievalSurfaceEntry:
    return WorkbenchRetrievalSurfaceEntry(
        entry_id="workbench_fact:project-1:document-1:fact-1",
        project_id="00000000-0000-0000-0000-000000000001",
        document_id="document-1",
        fact_id="fact-1",
        title="Бот отвечает клиентам в Telegram.",
        answer="Да, бот отвечает клиентам в Telegram.",
        search_text="Бот отвечает клиентам в Telegram.",
        embedding_text="Бот отвечает клиентам в Telegram.",
        embedding=(0.1, 0.2, 0.3),
        source_refs=("section-1",),
        enrichment={"contract": "faq_workbench_fact_retrieval_surface"},
    )


@pytest.mark.asyncio
async def test_replace_workbench_fact_runtime_surface_entries_upserts_entries_and_surface() -> (
    None
):
    connection = CapturingConnection()
    repository = WorkbenchRetrievalSurfaceRepository(connection)

    count = await repository.replace_workbench_fact_runtime_surface_entries(
        project_id="00000000-0000-0000-0000-000000000001",
        document_id="document-1",
        entries=(_entry(),),
    )

    assert count == 1
    joined_sql = "\\n".join(query for query, _args in connection.execute_calls)

    assert "delete from knowledge_retrieval_surface" in joined_sql
    assert "delete from knowledge_entries" in joined_sql
    assert "insert into knowledge_entries" in joined_sql
    assert "insert into knowledge_retrieval_surface" in joined_sql
    assert "faq_workbench_fact" in joined_sql
    assert "faq_workbench_runtime_projection_v1" in joined_sql
    assert "on conflict (id) do update" in joined_sql
    assert "on conflict (entry_id) do update" in joined_sql

    surface_args = connection.execute_calls[-1][1]
    assert "[0.1,0.2,0.3]" in surface_args


@pytest.mark.asyncio
async def test_replace_with_empty_entries_removes_existing_workbench_projection() -> (
    None
):
    connection = CapturingConnection()
    repository = WorkbenchRetrievalSurfaceRepository(connection)

    count = await repository.replace_workbench_fact_runtime_surface_entries(
        project_id="00000000-0000-0000-0000-000000000001",
        document_id="document-1",
        entries=(),
    )

    assert count == 0
    assert len(connection.execute_calls) == 2
    assert "delete from knowledge_retrieval_surface" in connection.execute_calls[0][0]
    assert "delete from knowledge_entries" in connection.execute_calls[1][0]
