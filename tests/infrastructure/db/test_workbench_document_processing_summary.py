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
async def test_persist_document_processing_summary_before_purge_writes_durable_document_summary() -> (
    None
):
    connection = CapturingConnection()
    repository = KnowledgeWorkbenchRepository(connection)

    await repository.persist_document_processing_summary_before_purge(
        project_id="00000000-0000-0000-0000-000000000001",
        document_id="document-1",
        processing_run_id="run-1",
    )

    assert len(connection.execute_calls) == 1
    query, args = connection.execute_calls[0]

    assert "update knowledge_workbench_documents" in query
    assert "processing_summary = jsonb_strip_nulls" in query
    assert "workbench_document_processing_summary_v1" in query
    assert "knowledge_workbench_processing_runs" in query
    assert "knowledge_workbench_processing_node_runs" in query
    assert "knowledge_workbench_processing_node_artifacts" in query
    assert "knowledge_workbench_registry_snapshots" in query
    assert "knowledge_workbench_canonical_facts" in query
    assert "knowledge_workbench_fact_relations" in query
    assert "knowledge_workbench_surfaces" in query
    assert "knowledge_retrieval_surface" in query

    for key in (
        "active_elapsed_seconds",
        "wall_elapsed_seconds",
        "total_prompt_tokens",
        "total_completion_tokens",
        "total_tokens",
        "total_llm_calls",
        "document_section_count",
        "prompt_a_artifact_count",
        "prompt_c_artifact_count",
        "canonical_fact_count",
        "fact_relation_count",
        "published_surface_count",
        "published_runtime_fact_count",
        "published_at",
    ):
        assert key in query

    assert args == (
        "00000000-0000-0000-0000-000000000001",
        "document-1",
        "run-1",
    )


@pytest.mark.asyncio
async def test_publication_purge_persists_summary_before_deleting_processing_workspace() -> (
    None
):
    connection = CapturingConnection()
    repository = KnowledgeWorkbenchRepository(connection)

    await repository.purge_transient_processing_workspace_after_publication(
        project_id="00000000-0000-0000-0000-000000000001",
        document_id="document-1",
        processing_run_id="run-1",
    )

    queries = [query for query, _args in connection.execute_calls]
    joined_sql = "\\n".join(queries)

    summary_index = next(
        index
        for index, query in enumerate(queries)
        if "processing_summary = jsonb_strip_nulls" in query
    )
    processing_run_delete_index = next(
        index
        for index, query in enumerate(queries)
        if "delete from knowledge_workbench_processing_runs" in query
    )

    assert summary_index < processing_run_delete_index
    assert "delete from knowledge_workbench_local_claim_retrieval_entries" in joined_sql
    assert "delete from knowledge_workbench_processing_runs" in joined_sql
    assert "retention_state = 'transient_purged'" in joined_sql
