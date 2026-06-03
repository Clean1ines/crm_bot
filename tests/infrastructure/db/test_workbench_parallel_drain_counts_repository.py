from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

import pytest

from src.infrastructure.db.knowledge_workbench_repository import (
    KnowledgeWorkbenchRepository,
)


@dataclass(slots=True)
class FakeConnection:
    fetchrow_results: list[Mapping[str, object] | None]
    fetchrow_calls: list[tuple[str, tuple[object, ...]]] = field(default_factory=list)

    async def fetchrow(self, query: str, *args: object) -> Mapping[str, object] | None:
        self.fetchrow_calls.append((query, args))
        if not self.fetchrow_results:
            raise AssertionError("unexpected fetchrow call")
        return self.fetchrow_results.pop(0)


@pytest.mark.asyncio
async def test_get_parallel_processing_drain_counts_maps_section_and_registry_queue_states() -> None:
    connection = FakeConnection(
        fetchrow_results=[
            {
                "section_ready": 0,
                "section_leased": 0,
                "section_claim_observations_persisted": 0,
                "section_registry_application_queued": 1,
                "section_waiting_for_fresh_registry": 0,
                "section_failed": 0,
                "section_registry_application_applied": 2,
                "section_skipped": 1,
            },
            {
                "registry_ready": 1,
                "registry_leased": 0,
                "registry_waiting_for_fresh_registry": 1,
                "registry_failed": 0,
                "registry_applied": 2,
                "registry_superseded": 1,
            },
        ]
    )
    repository = KnowledgeWorkbenchRepository(connection)

    counts = await repository.get_parallel_processing_drain_counts(
        project_id="project-1",
        document_id="document-1",
        processing_run_id="processing-run-1",
    )

    assert counts.section_registry_application_queued == 1
    assert counts.section_registry_application_applied == 2
    assert counts.section_skipped == 1
    assert counts.registry_ready == 1
    assert counts.registry_waiting_for_fresh_registry == 1
    assert counts.registry_applied == 2
    assert counts.registry_superseded == 1

    assert counts.active_section_work_count == 1
    assert counts.active_registry_work_count == 1
    assert counts.waiting_for_fresh_registry_count == 1
    assert counts.unfinished_work_count == 3
    assert counts.terminal_work_count == 6

    assert len(connection.fetchrow_calls) == 2

    section_query, section_args = connection.fetchrow_calls[0]
    registry_query, registry_args = connection.fetchrow_calls[1]
    normalized_section_query = " ".join(section_query.lower().split())
    normalized_registry_query = " ".join(registry_query.lower().split())

    assert "from knowledge_workbench_section_batch_queue_items" in normalized_section_query
    assert "registry_application_queued" in normalized_section_query
    assert "registry_application_applied" in normalized_section_query
    assert "skipped" in normalized_section_query

    assert "from knowledge_workbench_fact_registry_application_queue" in normalized_registry_query
    assert "ready" in normalized_registry_query
    assert "waiting_for_fresh_registry" in normalized_registry_query
    assert "applied" in normalized_registry_query
    assert "superseded" in normalized_registry_query

    assert section_args == ("project-1", "document-1", "processing-run-1")
    assert registry_args == ("project-1", "document-1", "processing-run-1")
