from __future__ import annotations

from dataclasses import dataclass

import pytest

from src.infrastructure.db.knowledge_workbench_repository import (
    KnowledgeWorkbenchRepository,
)


@dataclass(slots=True)
class CapturedFetchrow:
    query: str
    args: tuple[object, ...]


class FakeConnection:
    def __init__(self) -> None:
        self.fetchrow_calls: list[CapturedFetchrow] = []

    async def fetchrow(self, query: str, *args: object) -> dict[str, object]:
        self.fetchrow_calls.append(CapturedFetchrow(query=query, args=args))
        return {
            "document_sections_total": 3,
            "section_queue_items_total": 0,
            "claim_observation_artifacts_total": 0,
            "canonicalization_artifacts_total": 0,
        }


@pytest.mark.asyncio
async def test_get_parallel_processing_integrity_counts_reads_required_totals() -> None:
    connection = FakeConnection()
    repository = KnowledgeWorkbenchRepository(connection)

    counts = await repository.get_parallel_processing_integrity_counts(
        project_id="project-1",
        document_id="document-1",
        processing_run_id="processing-run-1",
    )

    assert counts.document_sections_total == 3
    assert counts.section_queue_items_total == 0
    assert counts.claim_observation_artifacts_total == 0
    assert counts.canonicalization_artifacts_total == 0

    assert len(connection.fetchrow_calls) == 1
    query = connection.fetchrow_calls[0].query

    assert "knowledge_workbench_document_sections" in query
    assert "knowledge_workbench_section_batch_queue_items" in query
    assert "knowledge_workbench_processing_node_artifacts" in query
    assert "faq_surface_claim_observations" in query
    assert "faq_surface_registry_merge" in query
    assert "section.status <> 'deleted'" in query
    assert connection.fetchrow_calls[0].args == (
        "project-1",
        "document-1",
        "processing-run-1",
    )
