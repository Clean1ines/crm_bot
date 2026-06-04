from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Mapping

import pytest

from src.domain.project_plane.knowledge_workbench.section_batch_queue import (
    SectionBatchQueueItemStatus,
)
from src.infrastructure.db.knowledge_workbench_repository import (
    KnowledgeWorkbenchRepository,
)


@dataclass(slots=True)
class FakeConnection:
    row: Mapping[str, object] | None = None
    fetchrow_calls: list[tuple[str, tuple[object, ...]]] = field(default_factory=list)

    async def fetchrow(self, query: str, *args: object) -> Mapping[str, object] | None:
        self.fetchrow_calls.append((query, args))
        return self.row


def _row() -> Mapping[str, object]:
    return {
        "queue_item_id": "section-batch-item-1",
        "batch_plan_id": "batch-plan-1",
        "processing_run_id": "processing-run-1",
        "project_id": "project-1",
        "document_id": "document-1",
        "section_id": "section-1",
        "section_key": "intro",
        "section_index": 0,
        "lane_id": "section-lane-1",
        "lane_index": 0,
        "observed_registry_snapshot_id": "registry-snapshot-1",
        "observed_registry_snapshot_sequence": 1,
        "status": SectionBatchQueueItemStatus.REGISTRY_APPLICATION_QUEUED.value,
        "claimed_by_worker_id": None,
        "lease_expires_at": None,
        "claim_observations_node_run_id": "claim-observations-node-run-1",
        "registry_application_queue_item_id": "registry-application-queue-item-1",
        "error_kind": None,
        "attempt_count": 1,
        "created_at": datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 6, 1, 12, 1, tzinfo=timezone.utc),
    }


@pytest.mark.asyncio
async def test_get_section_batch_queue_item_by_registry_application_queue_item_id_filters_and_maps_row() -> (
    None
):
    connection = FakeConnection(row=_row())
    repository = KnowledgeWorkbenchRepository(connection)

    item = await repository.get_section_batch_queue_item_by_registry_application_queue_item_id(
        project_id="project-1",
        document_id="document-1",
        processing_run_id="processing-run-1",
        registry_application_queue_item_id="registry-application-queue-item-1",
    )

    assert item is not None
    assert item.queue_item_id == "section-batch-item-1"
    assert item.status is SectionBatchQueueItemStatus.REGISTRY_APPLICATION_QUEUED
    assert item.claim_observations_node_run_id == "claim-observations-node-run-1"
    assert item.registry_application_queue_item_id == (
        "registry-application-queue-item-1"
    )

    assert len(connection.fetchrow_calls) == 1
    query, args = connection.fetchrow_calls[0]
    normalized_query = " ".join(query.lower().split())

    assert "from knowledge_workbench_section_batch_queue_items" in normalized_query
    assert "registry_application_queue_item_id = $4" in normalized_query
    assert "limit 1" in normalized_query
    assert args == (
        "project-1",
        "document-1",
        "processing-run-1",
        "registry-application-queue-item-1",
    )


@pytest.mark.asyncio
async def test_get_section_batch_queue_item_by_registry_application_queue_item_id_returns_none_when_missing() -> (
    None
):
    connection = FakeConnection(row=None)
    repository = KnowledgeWorkbenchRepository(connection)

    item = await repository.get_section_batch_queue_item_by_registry_application_queue_item_id(
        project_id="project-1",
        document_id="document-1",
        processing_run_id="processing-run-1",
        registry_application_queue_item_id="registry-application-queue-item-missing",
    )

    assert item is None
