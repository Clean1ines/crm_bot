from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Mapping

import pytest

from src.domain.project_plane.knowledge_workbench.section_batch_queue import (
    SectionBatchQueueItemStatus,
)
from src.infrastructure.db.knowledge_workbench_repository import (
    KnowledgeWorkbenchRepository,
)


@dataclass(slots=True)
class FakeTransaction:
    connection: FakeConnection

    async def __aenter__(self) -> None:
        self.connection.transaction_count += 1

    async def __aexit__(
        self,
        exc_type: object,
        exc: object,
        traceback: object,
    ) -> None:
        return None


@dataclass(slots=True)
class FakeConnection:
    execute_result: str = "UPDATE 0"
    fetchrow_result: Mapping[str, object] | None = None
    execute_calls: list[tuple[str, tuple[object, ...]]] = field(default_factory=list)
    fetchrow_calls: list[tuple[str, tuple[object, ...]]] = field(default_factory=list)
    transaction_count: int = 0

    def transaction(self) -> FakeTransaction:
        return FakeTransaction(self)

    async def execute(self, query: str, *args: object) -> str:
        self.execute_calls.append((query, args))
        return self.execute_result

    async def fetchrow(
        self,
        query: str,
        *args: object,
    ) -> Mapping[str, object] | None:
        self.fetchrow_calls.append((query, args))
        return self.fetchrow_result

    async def fetch(self, query: str, *args: object) -> list[Mapping[str, object]]:
        raise AssertionError("fetch must not be used by section work item leasing")


def _row(
    *,
    status: str = "leased",
    worker_id: str | None = "worker-1",
    lease_expires_at: datetime | None = None,
) -> Mapping[str, object]:
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
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
        "observed_registry_snapshot_id": "snapshot-1",
        "observed_registry_snapshot_sequence": 1,
        "status": status,
        "claimed_by_worker_id": worker_id,
        "lease_expires_at": lease_expires_at or now + timedelta(minutes=5),
        "claim_observations_node_run_id": None,
        "registry_application_queue_item_id": None,
        "error_kind": None,
        "attempt_count": 1,
        "created_at": now,
        "updated_at": now,
    }


@pytest.mark.asyncio
async def test_restore_stale_section_work_item_leases_returns_update_count() -> None:
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    connection = FakeConnection(execute_result="UPDATE 2")
    repository = KnowledgeWorkbenchRepository(connection)

    restored = await repository.restore_stale_section_work_item_leases(
        project_id="project-1",
        document_id="document-1",
        processing_run_id="processing-run-1",
        now=now,
    )

    assert restored == 2
    assert len(connection.execute_calls) == 1

    query, args = connection.execute_calls[0]
    normalized = " ".join(query.split())

    assert "knowledge_workbench_section_batch_queue_items" in normalized
    assert "status = 'ready'" in normalized
    assert "status = 'leased'" in normalized
    assert "lease_expires_at <= $4" in normalized
    assert args == ("project-1", "document-1", "processing-run-1", now)


@pytest.mark.asyncio
async def test_lease_next_ready_section_work_item_uses_skip_locked_and_maps_item() -> (
    None
):
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    lease_expires_at = now + timedelta(minutes=5)
    connection = FakeConnection(fetchrow_result=_row(lease_expires_at=lease_expires_at))
    repository = KnowledgeWorkbenchRepository(connection)

    item = await repository.lease_next_ready_section_work_item(
        project_id="project-1",
        document_id="document-1",
        processing_run_id="processing-run-1",
        worker_id="worker-1",
        lease_expires_at=lease_expires_at,
        now=now,
    )

    assert item is not None
    assert item.status is SectionBatchQueueItemStatus.LEASED
    assert item.claimed_by_worker_id == "worker-1"
    assert item.lease_expires_at == lease_expires_at
    assert item.attempt_count == 1
    assert connection.transaction_count == 1

    query, args = connection.fetchrow_calls[0]
    normalized = " ".join(query.split())

    assert "FOR UPDATE SKIP LOCKED" in normalized
    assert "status = 'ready'" in normalized
    assert "status = 'leased'" in normalized
    assert "attempt_count = item.attempt_count + 1" in normalized
    assert args == (
        "project-1",
        "document-1",
        "processing-run-1",
        "worker-1",
        lease_expires_at,
        now,
    )


@pytest.mark.asyncio
async def test_lease_next_ready_section_work_item_returns_none_without_ready_item() -> (
    None
):
    now = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    connection = FakeConnection(fetchrow_result=None)
    repository = KnowledgeWorkbenchRepository(connection)

    item = await repository.lease_next_ready_section_work_item(
        project_id="project-1",
        document_id="document-1",
        processing_run_id="processing-run-1",
        worker_id="worker-1",
        lease_expires_at=now + timedelta(minutes=5),
        now=now,
    )

    assert item is None
    assert connection.transaction_count == 1
