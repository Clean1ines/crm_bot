from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from src.domain.project_plane.knowledge_workbench import (
    RegistryApplicationQueueItem,
    RegistryApplicationQueueItemStatus,
)
from src.infrastructure.db.knowledge_workbench_repository import (
    KnowledgeWorkbenchRepository,
)


@dataclass(slots=True)
class FakeConnection:
    executed: list[tuple[str, tuple[object, ...]]] = field(default_factory=list)
    fetchrow_result: dict[str, object] | None = None

    async def execute(self, query: str, *args: object) -> str:
        self.executed.append((query, args))
        return "UPDATE 1"

    async def fetchrow(self, query: str, *args: object):
        self.executed.append((query, args))
        return self.fetchrow_result

    async def fetch(self, query: str, *args: object):
        self.executed.append((query, args))
        return []


def _queue_item() -> RegistryApplicationQueueItem:
    return RegistryApplicationQueueItem(
        queue_item_id="queue-item-1",
        processing_run_id="processing-run-1",
        project_id="00000000-0000-0000-0000-000000000001",
        document_id="document-1",
        section_id="section-1",
        source_node_run_id="node-run-section-1",
        observed_registry_snapshot_id="snapshot-1",
        observed_registry_snapshot_sequence=1,
        claim_input_refs=("finding-1", "finding-2"),
        status=RegistryApplicationQueueItemStatus.READY,
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )


@pytest.mark.asyncio
async def test_create_registry_application_queue_items_persists_snapshot_freshness_metadata() -> (
    None
):
    connection = FakeConnection()
    repository = KnowledgeWorkbenchRepository(connection)

    await repository.create_registry_application_queue_items((_queue_item(),))

    assert len(connection.executed) == 1
    query, args = connection.executed[0]

    assert "knowledge_workbench_registry_application_queue" in query
    assert "observed_registry_snapshot_id" in query
    assert "observed_registry_snapshot_sequence" in query
    assert args[0] == "queue-item-1"
    assert args[6] == "snapshot-1"
    assert args[7] == 1
    assert args[9] == "ready"


@pytest.mark.asyncio
async def test_lease_next_registry_application_queue_item_returns_domain_item() -> None:
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    connection = FakeConnection(
        fetchrow_result={
            "queue_item_id": "queue-item-1",
            "processing_run_id": "processing-run-1",
            "project_id": "00000000-0000-0000-0000-000000000001",
            "document_id": "document-1",
            "section_id": "section-1",
            "source_node_run_id": "node-run-section-1",
            "observed_registry_snapshot_id": "snapshot-1",
            "observed_registry_snapshot_sequence": 1,
            "claim_input_refs": ["finding-1"],
            "status": "leased",
            "claimed_by_worker_id": "worker-1",
            "lease_expires_at": now,
            "applied_registry_snapshot_id": None,
            "stale_at_registry_snapshot_id": None,
            "attempt_count": 1,
            "created_at": now,
            "updated_at": now,
        }
    )
    repository = KnowledgeWorkbenchRepository(connection)

    item = await repository.lease_next_registry_application_queue_item(
        project_id="00000000-0000-0000-0000-000000000001",
        document_id="document-1",
        processing_run_id="processing-run-1",
        worker_id="worker-1",
        lease_expires_at=now,
    )

    assert item is not None
    assert item.queue_item_id == "queue-item-1"
    assert item.status is RegistryApplicationQueueItemStatus.LEASED
    assert item.claimed_by_worker_id == "worker-1"
    assert item.claim_input_refs == ("finding-1",)

    query, args = connection.executed[0]
    assert "FOR UPDATE SKIP LOCKED" in query
    assert args[3] == "worker-1"


@pytest.mark.asyncio
async def test_mark_registry_application_queue_item_waiting_for_fresh_registry() -> (
    None
):
    connection = FakeConnection()
    repository = KnowledgeWorkbenchRepository(connection)

    await repository.mark_registry_application_queue_item_waiting_for_fresh_registry(
        queue_item_id="queue-item-1",
        stale_at_registry_snapshot_id="snapshot-2",
    )

    query, args = connection.executed[0]
    assert "waiting_for_fresh_registry" in query
    assert args == ("queue-item-1", "snapshot-2")


@pytest.mark.asyncio
async def test_mark_registry_application_queue_item_applied() -> None:
    connection = FakeConnection()
    repository = KnowledgeWorkbenchRepository(connection)

    await repository.mark_registry_application_queue_item_applied(
        queue_item_id="queue-item-1",
        applied_registry_snapshot_id="snapshot-2",
    )

    query, args = connection.executed[0]
    assert "status = 'applied'" in query
    assert args == ("queue-item-1", "snapshot-2")
