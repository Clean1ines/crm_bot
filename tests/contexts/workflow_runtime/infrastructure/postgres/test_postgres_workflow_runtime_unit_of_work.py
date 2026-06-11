from __future__ import annotations

from dataclasses import dataclass
from typing import cast

import asyncpg
import pytest

from src.contexts.workflow_runtime.application.ports.command_log_repository_port import (
    CommandLogRepositoryPort,
)
from src.contexts.workflow_runtime.application.ports.event_cursor_repository_port import (
    EventCursorRepositoryPort,
)
from src.contexts.workflow_runtime.application.ports.outbox_repository_port import (
    OutboxRepositoryPort,
)
from src.contexts.workflow_runtime.application.ports.progress_snapshot_repository_port import (
    ProgressSnapshotRepositoryPort,
)
from src.contexts.workflow_runtime.application.ports.resource_usage_repository_port import (
    ResourceUsageRepositoryPort,
)
from src.contexts.workflow_runtime.application.ports.timeline_repository_port import (
    TimelineRepositoryPort,
)
from src.contexts.workflow_runtime.infrastructure.postgres.postgres_workflow_runtime_unit_of_work import (
    PostgresWorkflowRuntimeUnitOfWork,
)


@dataclass(slots=True)
class FakeTransaction:
    started: bool = False
    committed: bool = False
    rolled_back: bool = False

    async def start(self) -> None:
        self.started = True

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


@dataclass(slots=True)
class FakeConnection:
    transaction_obj: FakeTransaction

    def transaction(self) -> FakeTransaction:
        return self.transaction_obj


@pytest.mark.asyncio
async def test_uow_exposes_command_log_outbox_event_cursors() -> None:
    unit_of_work = PostgresWorkflowRuntimeUnitOfWork(
        cast(asyncpg.Connection, FakeConnection(FakeTransaction())),
    )

    await unit_of_work.start()

    assert isinstance(unit_of_work.command_log, CommandLogRepositoryPort)
    assert isinstance(unit_of_work.outbox, OutboxRepositoryPort)
    assert isinstance(unit_of_work.event_cursors, EventCursorRepositoryPort)
    assert isinstance(unit_of_work.progress_snapshots, ProgressSnapshotRepositoryPort)
    assert isinstance(unit_of_work.timeline, TimelineRepositoryPort)
    assert isinstance(unit_of_work.resource_usage, ResourceUsageRepositoryPort)


@pytest.mark.asyncio
async def test_commit_persists_command_event_cursor_transaction() -> None:
    transaction = FakeTransaction()
    unit_of_work = PostgresWorkflowRuntimeUnitOfWork(
        cast(asyncpg.Connection, FakeConnection(transaction)),
    )

    await unit_of_work.start()
    await unit_of_work.commit()

    assert transaction.started
    assert transaction.committed
    assert not transaction.rolled_back


@pytest.mark.asyncio
async def test_rollback_discards_command_event_cursor_transaction() -> None:
    transaction = FakeTransaction()
    unit_of_work = PostgresWorkflowRuntimeUnitOfWork(
        cast(asyncpg.Connection, FakeConnection(transaction)),
    )

    await unit_of_work.start()
    await unit_of_work.rollback()

    assert transaction.started
    assert transaction.rolled_back
    assert not transaction.committed


def test_uow_requires_start_before_repository_access() -> None:
    unit_of_work = PostgresWorkflowRuntimeUnitOfWork(
        cast(asyncpg.Connection, FakeConnection(FakeTransaction())),
    )

    with pytest.raises(RuntimeError, match="start"):
        _ = unit_of_work.command_log
