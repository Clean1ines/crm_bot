from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

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
from src.contexts.workflow_runtime.application.ports.workflow_runtime_unit_of_work_port import (
    WorkflowRuntimeUnitOfWorkPort,
)
from src.contexts.workflow_runtime.domain.entities.workflow_command import (
    WorkflowCommand,
    WorkflowCommandStatus,
)
from src.contexts.workflow_runtime.domain.entities.workflow_event import WorkflowEvent
from src.contexts.workflow_runtime.domain.entities.workflow_event_cursor import (
    WorkflowEventCursor,
)
from src.contexts.workflow_runtime.domain.entities.workflow_progress_snapshot import (
    WorkflowProgressSnapshot,
)
from src.contexts.workflow_runtime.domain.entities.workflow_resource_usage_snapshot import (
    WorkflowResourceUsageSnapshot,
)
from src.contexts.workflow_runtime.domain.entities.workflow_timeline_entry import (
    WorkflowTimelineEntry,
    WorkflowTimelineSeverity,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_command_id import (
    WorkflowCommandId,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_consumer_ref import (
    WorkflowConsumerRef,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_event_id import (
    WorkflowEventId,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_idempotency_key import (
    WorkflowIdempotencyKey,
)


def _now() -> datetime:
    return datetime(2026, 6, 11, 12, 0, tzinfo=timezone.utc)


def _command() -> WorkflowCommand:
    return WorkflowCommand(
        command_id=WorkflowCommandId("command-1"),
        command_type="IngestSourceDocument",
        workflow_run_id="workflow-1",
        idempotency_key=WorkflowIdempotencyKey("source-ingestion:workflow-1"),
        payload={},
        status=WorkflowCommandStatus.PENDING,
        run_after=_now(),
        created_at=_now(),
        updated_at=_now(),
    )


def _event() -> WorkflowEvent:
    return WorkflowEvent(
        event_id=WorkflowEventId("event-1"),
        event_type="SourceUnitsCreated",
        workflow_run_id="workflow-1",
        payload={},
        occurred_at=_now(),
        sequence_number=1,
    )


@dataclass(slots=True)
class FakeCommandLogRepository:
    command: WorkflowCommand | None = None

    async def append_pending_command(
        self,
        command: WorkflowCommand,
    ) -> WorkflowCommand:
        self.command = command
        return command

    async def mark_command_completed(
        self,
        *,
        command_id: WorkflowCommandId,
        completed_at: datetime,
    ) -> WorkflowCommand:
        if self.command is None:
            raise AssertionError("command was not appended")
        return WorkflowCommand(
            command_id=command_id,
            command_type=self.command.command_type,
            workflow_run_id=self.command.workflow_run_id,
            idempotency_key=self.command.idempotency_key,
            payload=self.command.payload,
            status=WorkflowCommandStatus.COMPLETED,
            run_after=self.command.run_after,
            created_at=self.command.created_at,
            updated_at=completed_at,
            attempt_count=self.command.attempt_count,
        )


@dataclass(slots=True)
class FakeOutboxRepository:
    events: list[WorkflowEvent] = field(default_factory=list)

    async def append_event(
        self,
        event: WorkflowEvent,
    ) -> WorkflowEvent:
        self.events.append(event)
        return event

    async def list_events_after(
        self,
        *,
        consumer_ref: WorkflowConsumerRef,
        after_sequence_number: int,
        limit: int,
    ) -> tuple[WorkflowEvent, ...]:
        del consumer_ref
        return tuple(
            event
            for event in self.events
            if event.sequence_number is not None
            and event.sequence_number > after_sequence_number
        )[:limit]


@dataclass(slots=True)
class FakeEventCursorRepository:
    cursor: WorkflowEventCursor | None = None

    async def get_cursor(
        self,
        consumer_ref: WorkflowConsumerRef,
    ) -> WorkflowEventCursor | None:
        if self.cursor is not None and self.cursor.consumer_ref == consumer_ref:
            return self.cursor
        return None

    async def save_cursor(
        self,
        cursor: WorkflowEventCursor,
    ) -> WorkflowEventCursor:
        self.cursor = cursor
        return cursor


@dataclass(slots=True)
class FakeProgressSnapshotRepository:
    snapshot: WorkflowProgressSnapshot | None = None

    async def get_snapshot(
        self,
        workflow_run_id: str,
    ) -> WorkflowProgressSnapshot | None:
        if (
            self.snapshot is not None
            and self.snapshot.workflow_run_id == workflow_run_id
        ):
            return self.snapshot
        return None

    async def save_snapshot(
        self,
        snapshot: WorkflowProgressSnapshot,
    ) -> WorkflowProgressSnapshot:
        self.snapshot = snapshot
        return snapshot


@dataclass(slots=True)
class FakeTimelineRepository:
    entries: list[WorkflowTimelineEntry] = field(default_factory=list)

    async def append_entry(
        self,
        entry: WorkflowTimelineEntry,
    ) -> WorkflowTimelineEntry:
        self.entries.append(entry)
        return entry

    async def list_recent_entries(
        self,
        *,
        workflow_run_id: str,
        limit: int,
    ) -> tuple[WorkflowTimelineEntry, ...]:
        return tuple(
            entry for entry in self.entries if entry.workflow_run_id == workflow_run_id
        )[:limit]


@dataclass(slots=True)
class FakeResourceUsageRepository:
    usage: WorkflowResourceUsageSnapshot | None = None

    async def get_usage(
        self,
        workflow_run_id: str,
    ) -> WorkflowResourceUsageSnapshot | None:
        if self.usage is not None and self.usage.workflow_run_id == workflow_run_id:
            return self.usage
        return None

    async def save_usage(
        self,
        usage: WorkflowResourceUsageSnapshot,
    ) -> WorkflowResourceUsageSnapshot:
        self.usage = usage
        return usage


@dataclass(slots=True)
class FakeWorkflowRuntimeUnitOfWork:
    command_log: FakeCommandLogRepository = field(
        default_factory=FakeCommandLogRepository,
    )
    outbox: FakeOutboxRepository = field(default_factory=FakeOutboxRepository)
    event_cursors: FakeEventCursorRepository = field(
        default_factory=FakeEventCursorRepository,
    )
    progress_snapshots: FakeProgressSnapshotRepository = field(
        default_factory=FakeProgressSnapshotRepository,
    )
    timeline: FakeTimelineRepository = field(default_factory=FakeTimelineRepository)
    resource_usage: FakeResourceUsageRepository = field(
        default_factory=FakeResourceUsageRepository,
    )
    committed: bool = False
    rolled_back: bool = False

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


async def _exercise_unit_of_work(
    unit_of_work: WorkflowRuntimeUnitOfWorkPort,
) -> None:
    command = await unit_of_work.command_log.append_pending_command(_command())
    await unit_of_work.command_log.mark_command_completed(
        command_id=command.command_id,
        completed_at=_now(),
    )

    event = await unit_of_work.outbox.append_event(_event())
    events = await unit_of_work.outbox.list_events_after(
        consumer_ref=WorkflowConsumerRef("knowledge-extraction-saga"),
        after_sequence_number=0,
        limit=10,
    )
    assert events == (event,)

    cursor = WorkflowEventCursor(
        consumer_ref=WorkflowConsumerRef("knowledge-extraction-saga"),
        last_seen_sequence_number=0,
        updated_at=_now(),
    )
    await unit_of_work.event_cursors.save_cursor(cursor)
    loaded_cursor = await unit_of_work.event_cursors.get_cursor(cursor.consumer_ref)
    assert loaded_cursor == cursor

    snapshot = WorkflowProgressSnapshot(
        workflow_run_id="workflow-1",
        current_phase="SOURCE_INGESTION",
        workflow_status="RUNNING",
        updated_at=_now(),
    )
    await unit_of_work.progress_snapshots.save_snapshot(snapshot)
    assert await unit_of_work.progress_snapshots.get_snapshot("workflow-1") == snapshot

    entry = WorkflowTimelineEntry(
        timeline_entry_id="entry-1",
        workflow_run_id="workflow-1",
        event_type="SOURCE_UNITS_CREATED",
        phase="SOURCE_INGESTION",
        severity=WorkflowTimelineSeverity.INFO,
        message="Source units created",
        payload_summary={},
        occurred_at=_now(),
    )
    await unit_of_work.timeline.append_entry(entry)
    assert await unit_of_work.timeline.list_recent_entries(
        workflow_run_id="workflow-1",
        limit=10,
    ) == (entry,)

    usage = WorkflowResourceUsageSnapshot(
        workflow_run_id="workflow-1",
        updated_at=_now(),
    )
    await unit_of_work.resource_usage.save_usage(usage)
    assert await unit_of_work.resource_usage.get_usage("workflow-1") == usage

    await unit_of_work.commit()


def test_ports_are_runtime_checkable_protocols() -> None:
    unit_of_work = FakeWorkflowRuntimeUnitOfWork()

    assert isinstance(unit_of_work.command_log, CommandLogRepositoryPort)
    assert isinstance(unit_of_work.outbox, OutboxRepositoryPort)
    assert isinstance(unit_of_work.event_cursors, EventCursorRepositoryPort)
    assert isinstance(unit_of_work.progress_snapshots, ProgressSnapshotRepositoryPort)
    assert isinstance(unit_of_work.timeline, TimelineRepositoryPort)
    assert isinstance(unit_of_work.resource_usage, ResourceUsageRepositoryPort)
    assert isinstance(unit_of_work, WorkflowRuntimeUnitOfWorkPort)


async def test_ports_are_structurally_usable() -> None:
    unit_of_work = FakeWorkflowRuntimeUnitOfWork()

    await _exercise_unit_of_work(unit_of_work)

    assert unit_of_work.committed is True
    assert unit_of_work.rolled_back is False
