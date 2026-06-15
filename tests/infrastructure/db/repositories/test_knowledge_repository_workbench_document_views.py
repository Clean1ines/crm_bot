from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

import pytest

from src.infrastructure.db.repositories.knowledge_document_queries import (
    get_document_detail,
    list_project_documents,
)


@dataclass(slots=True)
class _Connection:
    rows: list[dict[str, object]]
    queries: list[str]

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        del args
        self.queries.append(query)
        return self.rows

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        del args
        self.queries.append(query)
        return self.rows[0] if self.rows else None


def _base_row() -> dict[str, object]:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return {
        "id": UUID("11111111-1111-1111-1111-111111111111"),
        "project_id": UUID("22222222-2222-2222-2222-222222222222"),
        "file_name": "source.md",
        "file_size": 123,
        "status": "processed",
        "error": None,
        "uploaded_by": "tester",
        "created_at": now,
        "updated_at": now,
        "preprocessing_mode": "faq",
        "preprocessing_status": "completed",
        "preprocessing_error": None,
        "preprocessing_model": "model",
        "preprocessing_prompt_version": "v1",
        "preprocessing_metrics": {},
        "source_unit_count": 7,
        "draft_claim_count": 11,
        "draft_claim_embedding_count": 10,
        "curated_item_count": 8,
        "runtime_entry_count": 6,
        "runtime_embedding_count": 5,
        "publication_count": 1,
        "llm_tokens_input": 100,
        "llm_tokens_output": 50,
        "llm_tokens_total": 150,
        "llm_usage_events_count": 2,
        "llm_models": "provider: model",
    }


def _combined_queries(queries: Iterable[str]) -> str:
    return "\\n".join(queries)


@pytest.mark.asyncio
async def test_document_list_uses_workbench_counters_for_legacy_transport_fields() -> (
    None
):
    connection = _Connection(rows=[_base_row()], queries=[])

    documents = await list_project_documents(
        connection,
        project_id="22222222-2222-2222-2222-222222222222",
    )

    assert documents[0].chunk_count == 7
    assert documents[0].structured_entries == 6
    assert documents[0].structured_chunk_count == 5
    assert documents[0].source_unit_count == 7
    assert documents[0].draft_claim_count == 11
    assert documents[0].draft_claim_embedding_count == 10
    assert documents[0].curated_item_count == 8
    assert documents[0].runtime_entry_count == 6
    assert documents[0].runtime_embedding_count == 5
    assert documents[0].publication_count == 1

    query = _combined_queries(connection.queries)
    assert "source_units" in query
    assert "draft_claim_observations" in query
    assert "knowledge_workbench_runtime_retrieval_entries" in query
    assert "knowledge_workbench_runtime_retrieval_entry_embeddings" in query
    assert "knowledge_" + "entries" not in query
    assert "knowledge_" + "retrieval_" + "surface" not in query
    assert "knowledge_" + "source_" + "chunks" not in query


@pytest.mark.asyncio
async def test_document_detail_uses_workbench_runtime_embedding_count() -> None:
    connection = _Connection(rows=[_base_row()], queries=[])

    document = await get_document_detail(
        connection,
        document_id="11111111-1111-1111-1111-111111111111",
    )

    assert document is not None
    assert document.chunk_count == 7
    assert document.structured_entries == 6
    assert document.structured_chunk_count == 5
    assert document.runtime_embedding_count == 5

    query = _combined_queries(connection.queries)
    assert "knowledge_workbench_runtime_retrieval_entry_embeddings" in query
    assert "knowledge_" + "entries" not in query
    assert "knowledge_" + "retrieval_" + "surface" not in query
