from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone

import pytest

from src.contexts.knowledge_workbench.application.sagas.apply_source_ingestion_workflow_effects import (
    ApplySourceIngestionWorkflowEffects,
    ApplySourceIngestionWorkflowEffectsCommand,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalCommandType,
    KnowledgeExtractionCanonicalEventType,
)
from src.contexts.knowledge_workbench.application.sagas.source_ingestion_workflow_effects import (
    BuildSourceIngestionWorkflowEffects,
    BuildSourceIngestionWorkflowEffectsCommand,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_format import (
    SourceFormat,
)
from src.contexts.knowledge_workbench.observability.application.models.frontend_workflow_event import (
    FrontendWorkflowEvent,
)
from src.contexts.knowledge_workbench.observability.application.projectors.project_frontend_workflow_event import (
    ProjectFrontendWorkflowEvent,
)
from src.contexts.knowledge_workbench.observability.application.projectors.source_ingestion_frontend_workflow_event_projector import (
    SourceIngestionFrontendWorkflowEventProjector,
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
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_command_id import (
    WorkflowCommandId,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_consumer_ref import (
    WorkflowConsumerRef,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_idempotency_key import (
    WorkflowIdempotencyKey,
)


def _now() -> datetime:
    return datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)


def _effects():
    return BuildSourceIngestionWorkflowEffects().execute(
        BuildSourceIngestionWorkflowEffectsCommand(
            workflow_run_id="knowledge-extraction:source-document:project-1:abc",
            project_id="project-1",
            source_document_ref="source-document:project-1:abc",
            source_unit_count=3,
            source_format=SourceFormat.MARKDOWN,
            content_hash="sha256:abc",
            occurred_at=_now(),
        )
    )


@dataclass(slots=True)
class FakeCommandLogRepository:
    commands_by_id: dict[WorkflowCommandId, WorkflowCommand] = field(
        default_factory=dict
    )
    commands_by_idempotency_key: dict[WorkflowIdempotencyKey, WorkflowCommand] = field(
        default_factory=dict
    )

    async def append_pending_command(
        self,
        command: WorkflowCommand,
    ) -> WorkflowCommand:
        existing = self.commands_by_idempotency_key.get(command.idempotency_key)
        if existing is not None:
            return existing
        self.commands_by_id[command.command_id] = command
        self.commands_by_idempotency_key[command.idempotency_key] = command
        return command

    async def mark_command_completed(
        self,
        *,
        command_id: WorkflowCommandId,
        completed_at: datetime,
    ) -> WorkflowCommand:
        command = self.commands_by_id[command_id]
        completed = WorkflowCommand(
            command_id=command.command_id,
            command_type=command.command_type,
            workflow_run_id=command.workflow_run_id,
            idempotency_key=command.idempotency_key,
            payload=command.payload,
            status=WorkflowCommandStatus.COMPLETED,
            run_after=command.run_after,
            created_at=command.created_at,
            updated_at=completed_at,
            attempt_count=command.attempt_count,
        )
        self.commands_by_id[command_id] = completed
        self.commands_by_idempotency_key[completed.idempotency_key] = completed
        return completed


@dataclass(slots=True)
class FakeOutboxRepository:
    events: list[WorkflowEvent] = field(default_factory=list)

    async def append_event(self, event: WorkflowEvent) -> WorkflowEvent:
        persisted = replace(event, sequence_number=len(self.events) + 1)
        self.events.append(persisted)
        return persisted

    async def list_events_after(
        self,
        *,
        consumer_ref: WorkflowConsumerRef,
        after_sequence_number: int,
        limit: int,
    ) -> tuple[WorkflowEvent, ...]:
        del consumer_ref, after_sequence_number, limit
        return tuple(self.events)


@dataclass(slots=True)
class FakeEventCursorRepository:
    async def get_cursor(
        self,
        consumer_ref: WorkflowConsumerRef,
    ) -> WorkflowEventCursor | None:
        del consumer_ref
        return None

    async def save_cursor(
        self,
        cursor: WorkflowEventCursor,
    ) -> WorkflowEventCursor:
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
        default_factory=FakeCommandLogRepository
    )
    outbox: FakeOutboxRepository = field(default_factory=FakeOutboxRepository)
    event_cursors: FakeEventCursorRepository = field(
        default_factory=FakeEventCursorRepository
    )
    progress_snapshots: FakeProgressSnapshotRepository = field(
        default_factory=FakeProgressSnapshotRepository
    )
    timeline: FakeTimelineRepository = field(default_factory=FakeTimelineRepository)
    resource_usage: FakeResourceUsageRepository = field(
        default_factory=FakeResourceUsageRepository
    )

    async def commit(self) -> None:
        raise AssertionError("applier must not own transaction commit")

    async def rollback(self) -> None:
        raise AssertionError("applier must not own transaction rollback")


@dataclass(slots=True)
class InMemoryFrontendWorkflowEventRepository:
    events: dict[str, FrontendWorkflowEvent] = field(default_factory=dict)

    async def append(self, event: FrontendWorkflowEvent) -> FrontendWorkflowEvent:
        existing = self.events.get(event.projection_event_id)
        if existing is not None:
            return existing
        self.events[event.projection_event_id] = event
        return event


@pytest.mark.asyncio
async def test_marks_ingest_source_document_command_completed() -> None:
    unit_of_work = FakeWorkflowRuntimeUnitOfWork()

    result = await ApplySourceIngestionWorkflowEffects().execute(
        ApplySourceIngestionWorkflowEffectsCommand(effects=_effects()),
        unit_of_work=unit_of_work,
    )

    completed = unit_of_work.command_log.commands_by_id[
        WorkflowCommandId(
            "workflow-command:source-ingestion:"
            "knowledge-extraction:source-document:project-1:abc"
        )
    ]
    assert (
        result.completed_command_type
        is KnowledgeExtractionCanonicalCommandType.INGEST_SOURCE_DOCUMENT
    )
    assert completed.status is WorkflowCommandStatus.COMPLETED
    assert completed.payload["source_unit_count"] == 3


@pytest.mark.asyncio
async def test_appends_source_document_and_source_units_outbox_events() -> None:
    unit_of_work = FakeWorkflowRuntimeUnitOfWork()

    await ApplySourceIngestionWorkflowEffects().execute(
        ApplySourceIngestionWorkflowEffectsCommand(effects=_effects()),
        unit_of_work=unit_of_work,
    )

    assert tuple(event.event_type for event in unit_of_work.outbox.events) == (
        KnowledgeExtractionCanonicalEventType.SOURCE_DOCUMENT_PERSISTED.value,
        KnowledgeExtractionCanonicalEventType.SOURCE_UNITS_CREATED.value,
    )


@pytest.mark.asyncio
async def test_projects_persisted_source_ingestion_events_once() -> None:
    unit_of_work = FakeWorkflowRuntimeUnitOfWork()
    repository = InMemoryFrontendWorkflowEventRepository()
    projection_writer = ProjectFrontendWorkflowEvent(
        projector=SourceIngestionFrontendWorkflowEventProjector(),
        repository=repository,
    )

    await ApplySourceIngestionWorkflowEffects().execute(
        ApplySourceIngestionWorkflowEffectsCommand(effects=_effects()),
        unit_of_work=unit_of_work,
        frontend_event_projection_writer=projection_writer,
    )

    assert tuple(event.event_type for event in unit_of_work.outbox.events) == (
        KnowledgeExtractionCanonicalEventType.SOURCE_DOCUMENT_PERSISTED.value,
        KnowledgeExtractionCanonicalEventType.SOURCE_UNITS_CREATED.value,
    )
    assert tuple(repository.events) == (
        "frontend-workflow-event:"
        "workflow-event:knowledge-extraction:source-document:project-1:abc:"
        "SourceDocumentPersisted:source-document:project-1:abc:"
        "workflow_source_document_persisted:v1",
        "frontend-workflow-event:"
        "workflow-event:knowledge-extraction:source-document:project-1:abc:"
        "SOURCE_UNITS_CREATED:source-document:project-1:abc:source-units:"
        "workflow_source_units_created:v1",
    )


@pytest.mark.asyncio
async def test_appends_schedule_claim_builder_section_work_next_command() -> None:
    unit_of_work = FakeWorkflowRuntimeUnitOfWork()

    result = await ApplySourceIngestionWorkflowEffects().execute(
        ApplySourceIngestionWorkflowEffectsCommand(effects=_effects()),
        unit_of_work=unit_of_work,
    )

    pending = unit_of_work.command_log.commands_by_id[
        WorkflowCommandId(
            "workflow-command:schedule-claim-builder-section-work:"
            "knowledge-extraction:source-document:project-1:abc"
        )
    ]
    assert result.appended_next_command_count == 1
    assert (
        pending.command_type
        == KnowledgeExtractionCanonicalCommandType.SCHEDULE_CLAIM_BUILDER_SECTION_WORK.value
    )
    assert pending.status is WorkflowCommandStatus.PENDING


@pytest.mark.asyncio
async def test_saves_progress_snapshot_with_source_unit_count() -> None:
    unit_of_work = FakeWorkflowRuntimeUnitOfWork()

    await ApplySourceIngestionWorkflowEffects().execute(
        ApplySourceIngestionWorkflowEffectsCommand(effects=_effects()),
        unit_of_work=unit_of_work,
    )

    snapshot = unit_of_work.progress_snapshots.snapshot
    assert snapshot is not None
    assert snapshot.current_phase == "SOURCE_INGESTION"
    assert snapshot.workflow_status == "RUNNING"
    assert snapshot.total_work_items == 3
    assert snapshot.completed_work_items == 3
    assert snapshot.domain_counters["source_unit_count"] == 3


@pytest.mark.asyncio
async def test_appends_timeline_entries_for_command_events_and_next_command() -> None:
    unit_of_work = FakeWorkflowRuntimeUnitOfWork()

    result = await ApplySourceIngestionWorkflowEffects().execute(
        ApplySourceIngestionWorkflowEffectsCommand(effects=_effects()),
        unit_of_work=unit_of_work,
    )

    assert result.appended_timeline_entry_count == 4
    assert tuple(entry.message for entry in unit_of_work.timeline.entries) == (
        "Source ingestion command completed",
        "Source document persisted",
        "Source units created",
        "Claim builder section work scheduling requested",
    )


@pytest.mark.asyncio
async def test_saves_zero_resource_usage_snapshot() -> None:
    unit_of_work = FakeWorkflowRuntimeUnitOfWork()

    result = await ApplySourceIngestionWorkflowEffects().execute(
        ApplySourceIngestionWorkflowEffectsCommand(effects=_effects()),
        unit_of_work=unit_of_work,
    )

    usage = unit_of_work.resource_usage.usage
    assert result.saved_resource_usage is True
    assert usage is not None
    assert usage.request_count == 0
    assert usage.input_tokens == 0
    assert usage.output_tokens == 0
    assert usage.total_tokens == 0
    assert usage.estimated_cost_microusd == 0
    assert usage.duration_ms == 0
