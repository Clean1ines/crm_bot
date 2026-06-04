from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Mapping, Sequence

import pytest

from src.application.services.faq_workbench_local_claim_retrieval_surface_indexing_service import (
    LocalClaimRetrievalSurfaceEntry,
)
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
    fetchrow_calls: list[tuple[str, tuple[object, ...]]] = field(default_factory=list)
    indexed_row: Mapping[str, object] | None = None

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
        self.fetchrow_calls.append((" ".join(query.lower().split()), args))
        return self.indexed_row

    async def fetch(
        self,
        query: str,
        *args: object,
    ) -> Sequence[Mapping[str, object]]:
        raise AssertionError(f"unexpected fetch call: {query} {args}")


def _entry() -> LocalClaimRetrievalSurfaceEntry:
    return LocalClaimRetrievalSurfaceEntry(
        entry_id="local_claim:project-1:document-1:run-1:section-1:node-1:c1",
        project_id="00000000-0000-0000-0000-000000000001",
        document_id="document-1",
        processing_run_id="run-1",
        section_id="section-1",
        node_run_id="node-1",
        search_document_id="section-1:node-1:c1",
        local_ref="c1",
        claim="Бот отвечает клиентам в Telegram.",
        claim_kind="capability",
        granularity="atomic",
        search_text="Бот отвечает клиентам в Telegram. Может ли бот отвечать?",
        triple_texts=("бот отвечает клиентам",),
        possible_questions=("Может ли бот отвечать клиентам?",),
        scope="Telegram support",
        exclusion_scope="",
        evidence_block="Бот отвечает клиентам в Telegram.",
        relation_texts=("same_meaning c2",),
        embedding=(0.1, 0.2, 0.3),
        status="indexed",
    )


@pytest.mark.asyncio
async def test_has_indexed_local_claim_retrieval_entries_for_node_run_uses_indexed_status_probe() -> (
    None
):
    connection = CapturingConnection(indexed_row={"indexed": 1})
    repository = KnowledgeWorkbenchRepository(connection)

    indexed = await repository.has_indexed_local_claim_retrieval_entries_for_node_run(
        project_id="00000000-0000-0000-0000-000000000001",
        document_id="document-1",
        processing_run_id="run-1",
        node_run_id="node-1",
    )

    assert indexed is True
    assert len(connection.fetchrow_calls) == 1

    query, args = connection.fetchrow_calls[0]
    assert "from knowledge_workbench_local_claim_retrieval_entries" in query
    assert "node_run_id = $4" in query
    assert "status = 'indexed'" in query
    assert "limit 1" in query
    assert args == (
        "00000000-0000-0000-0000-000000000001",
        "document-1",
        "run-1",
        "node-1",
    )


@pytest.mark.asyncio
async def test_has_indexed_local_claim_retrieval_entries_for_node_run_returns_false_when_missing() -> (
    None
):
    connection = CapturingConnection(indexed_row=None)
    repository = KnowledgeWorkbenchRepository(connection)

    indexed = await repository.has_indexed_local_claim_retrieval_entries_for_node_run(
        project_id="00000000-0000-0000-0000-000000000001",
        document_id="document-1",
        processing_run_id="run-1",
        node_run_id="node-1",
    )

    assert indexed is False


@pytest.mark.asyncio
async def test_replace_local_claim_retrieval_entries_deletes_run_projection_and_upserts_vector_rows() -> (
    None
):
    connection = CapturingConnection()
    repository = KnowledgeWorkbenchRepository(connection)

    count = await repository.replace_local_claim_retrieval_entries(
        project_id="00000000-0000-0000-0000-000000000001",
        document_id="document-1",
        processing_run_id="run-1",
        entries=(_entry(),),
    )

    assert count == 1
    assert len(connection.execute_calls) == 2

    delete_query, delete_args = connection.execute_calls[0]
    insert_query, insert_args = connection.execute_calls[1]

    assert (
        "delete from knowledge_workbench_local_claim_retrieval_entries" in delete_query
    )
    assert "project_id = $1::uuid" in delete_query
    assert "document_id = $2" in delete_query
    assert "processing_run_id = $3" in delete_query
    assert delete_args == (
        "00000000-0000-0000-0000-000000000001",
        "document-1",
        "run-1",
    )

    assert (
        "insert into knowledge_workbench_local_claim_retrieval_entries" in insert_query
    )
    assert "embedding" in insert_query
    assert "$19::vector" in insert_query
    assert "on conflict (entry_id) do update set" in insert_query
    assert "updated_at = now()" in insert_query

    assert insert_args[0] == _entry().entry_id
    assert insert_args[18] == "[0.1,0.2,0.3]"
    assert insert_args[19] == "indexed"


@pytest.mark.asyncio
async def test_replace_local_claim_retrieval_entries_with_empty_entries_only_deletes_existing_projection() -> (
    None
):
    connection = CapturingConnection()
    repository = KnowledgeWorkbenchRepository(connection)

    count = await repository.replace_local_claim_retrieval_entries(
        project_id="00000000-0000-0000-0000-000000000001",
        document_id="document-1",
        processing_run_id="run-1",
        entries=(),
    )

    assert count == 0
    assert len(connection.execute_calls) == 1
    assert (
        "delete from knowledge_workbench_local_claim_retrieval_entries"
        in (connection.execute_calls[0][0])
    )
