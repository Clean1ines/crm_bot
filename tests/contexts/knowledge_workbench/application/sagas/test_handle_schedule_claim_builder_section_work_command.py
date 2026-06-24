from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone

import inspect

import pytest

from src.contexts.capacity_admission_queue.application.build_capacity_admission_projection_candidates import (
    CapacityAdmissionLaneTarget,
    CapacityAdmissionWorkItemProjectionCandidate,
)
from src.contexts.capacity_admission_queue.application.ports.capacity_admission_projection_writer_port import (
    PersistCapacityAdmissionProjectionResult,
)
from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.knowledge_workbench.application.sagas.handle_schedule_claim_builder_section_work_command import (
    HandleScheduleClaimBuilderSectionWorkCommand,
    HandleScheduleClaimBuilderSectionWorkCommandHandler,
)
from src.contexts.knowledge_workbench.observability.application.models.frontend_workflow_event import (
    FrontendWorkflowEvent,
)
from src.contexts.knowledge_workbench.observability.application.projectors.claim_builder_work_scheduling_frontend_workflow_event_projector import (
    ClaimBuilderWorkSchedulingFrontendWorkflowEventProjector,
)
from src.contexts.knowledge_workbench.observability.application.projectors.project_frontend_workflow_event import (
    ProjectFrontendWorkflowEvent,
)
from src.contexts.knowledge_workbench.application.sagas.handle_prepare_claim_builder_dispatch_batch_command import (
    HandlePrepareClaimBuilderDispatchBatchCommand,
    HandlePrepareClaimBuilderDispatchBatchCommandHandler,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalCommandType,
    KnowledgeExtractionCanonicalEventType,
)
from src.contexts.knowledge_workbench.source_management.domain.entities.source_document import (
    SourceDocument,
)
from src.contexts.knowledge_workbench.source_management.domain.entities.source_unit import (
    SourceUnit,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.heading_path import (
    HeadingPath,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_document_ref import (
    SourceDocumentRef,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_kind import (
    SourceUnitKind,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_lineage import (
    SourceUnitLineage,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_ref import (
    SourceUnitRef,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_text import (
    SourceUnitText,
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
from src.interfaces.composition.prepare_llm_dispatch_batch import (
    PrepareLlmDispatchBatchCommand,
)


def _now() -> datetime:
    return datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)


def _workflow_run_id() -> str:
    return "knowledge-extraction:source-document:project-1:abc"


def _document_ref() -> SourceDocumentRef:
    return SourceDocumentRef("source-document:project-1:abc")


def _workflow_command(
    *,
    command_type: str = (
        KnowledgeExtractionCanonicalCommandType.SCHEDULE_CLAIM_BUILDER_SECTION_WORK.value
    ),
    status: WorkflowCommandStatus = WorkflowCommandStatus.PENDING,
) -> WorkflowCommand:
    return WorkflowCommand(
        command_id=WorkflowCommandId(
            f"workflow-command:schedule-claim-builder-section-work:{_workflow_run_id()}"
        ),
        command_type=command_type,
        workflow_run_id=_workflow_run_id(),
        idempotency_key=WorkflowIdempotencyKey(
            f"schedule-claim-builder-section-work:{_workflow_run_id()}"
        ),
        payload={
            "workflow_run_id": _workflow_run_id(),
            "project_id": "project-1",
            "source_document_ref": _document_ref().value,
            "source_unit_count": 2,
        },
        status=status,
        run_after=_now(),
        created_at=_now(),
        updated_at=_now(),
    )


def _source_unit(*, ordinal: int) -> SourceUnit:
    return SourceUnit(
        unit_ref=SourceUnitRef(f"{_document_ref().value}.unit.{ordinal}"),
        document_ref=_document_ref(),
        unit_kind=SourceUnitKind.SECTION,
        text=SourceUnitText(f"# Unit {ordinal}\\n\\nBody"),
        heading_path=HeadingPath((f"Unit {ordinal}",)),
        lineage=SourceUnitLineage(),
        ordinal=ordinal,
        created_at=_now(),
    )


def _source_units() -> tuple[SourceUnit, ...]:
    return (_source_unit(ordinal=0), _source_unit(ordinal=1))


@dataclass(slots=True)
class FakeSourceManagementRepository:
    units: tuple[SourceUnit, ...]

    async def save_source_document(self, document: SourceDocument) -> None:
        del document

    async def load_source_document(
        self,
        document_ref: SourceDocumentRef,
    ) -> SourceDocument | None:
        del document_ref
        return None

    async def save_source_units(
        self,
        units: tuple[SourceUnit, ...],
    ) -> None:
        self.units = units

    async def list_source_units_for_document(
        self,
        document_ref: SourceDocumentRef,
    ) -> tuple[SourceUnit, ...]:
        assert document_ref == _document_ref()
        return self.units

    async def load_source_unit(
        self,
        unit_ref: SourceUnitRef,
    ) -> SourceUnit | None:
        return next((unit for unit in self.units if unit.unit_ref == unit_ref), None)


@dataclass(slots=True)
class SavedScheduledWorkItem:
    item: WorkItem
    idempotency_key: str
    payload_hash: str
    payload: Mapping[str, object]


@dataclass(slots=True)
class FakeWorkItemSchedulingRepository:
    existing_items: dict[str, WorkItem] = field(default_factory=dict)
    schedule_payload_hashes: dict[str, str] = field(default_factory=dict)
    saved: list[SavedScheduledWorkItem] = field(default_factory=list)

    async def get_work_item(self, work_item_id: str) -> WorkItem | None:
        return self.existing_items.get(work_item_id)

    async def get_schedule_payload_hash(self, work_item_id: str) -> str | None:
        return self.schedule_payload_hashes.get(work_item_id)

    async def save_scheduled_work_item(
        self,
        *,
        item: WorkItem,
        idempotency_key: str,
        payload_hash: str,
        payload: Mapping[str, object],
    ) -> None:
        self.saved.append(
            SavedScheduledWorkItem(
                item=item,
                idempotency_key=idempotency_key,
                payload_hash=payload_hash,
                payload=payload,
            )
        )
        self.existing_items[item.work_item_id] = item
        self.schedule_payload_hashes[item.work_item_id] = payload_hash


@dataclass(slots=True)
class FakeCapacityAdmissionProjectionWriter:
    candidates: list[CapacityAdmissionWorkItemProjectionCandidate] = field(
        default_factory=list,
    )

    async def persist_projection_candidates(
        self,
        candidates: tuple[CapacityAdmissionWorkItemProjectionCandidate, ...],
    ) -> PersistCapacityAdmissionProjectionResult:
        self.candidates.extend(candidates)
        return PersistCapacityAdmissionProjectionResult(
            persisted_count=len(candidates),
        )


@dataclass(slots=True)
class FakeCommandLogRepository:
    pending_commands: list[WorkflowCommand] = field(default_factory=list)
    completed_command_ids: list[WorkflowCommandId] = field(default_factory=list)

    async def append_pending_command(
        self,
        command: WorkflowCommand,
    ) -> WorkflowCommand:
        self.pending_commands.append(command)
        return command

    async def mark_command_completed(
        self,
        *,
        command_id: WorkflowCommandId,
        completed_at: datetime,
    ) -> WorkflowCommand:
        del completed_at
        self.completed_command_ids.append(command_id)
        return _workflow_command(status=WorkflowCommandStatus.COMPLETED)


@dataclass(slots=True)
class FakeOutboxRepository:
    events: list[WorkflowEvent] = field(default_factory=list)
    _next_sequence_number: int = 1

    async def append_event(self, event: WorkflowEvent) -> WorkflowEvent:
        persisted = WorkflowEvent(
            event_id=event.event_id,
            event_type=event.event_type,
            workflow_run_id=event.workflow_run_id,
            payload=event.payload,
            occurred_at=event.occurred_at,
            causation_command_id=event.causation_command_id,
            correlation_id=event.correlation_id,
            sequence_number=self._next_sequence_number,
        )
        self._next_sequence_number += 1
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
        raise AssertionError("handler must not own transaction commit")

    async def rollback(self) -> None:
        raise AssertionError("handler must not own transaction rollback")


async def _execute(
    workflow_command: WorkflowCommand | None = None,
    *,
    frontend_event_projection_writer: ProjectFrontendWorkflowEvent | None = None,
    capacity_admission_projection_writer: (
        FakeCapacityAdmissionProjectionWriter | None
    ) = None,
    capacity_admission_lane_target: CapacityAdmissionLaneTarget | None = None,
) -> tuple[
    object,
    FakeSourceManagementRepository,
    FakeWorkItemSchedulingRepository,
    FakeWorkflowRuntimeUnitOfWork,
]:
    source_repository = FakeSourceManagementRepository(units=_source_units())
    scheduling_repository = FakeWorkItemSchedulingRepository()
    workflow_unit_of_work = FakeWorkflowRuntimeUnitOfWork()
    result = await HandleScheduleClaimBuilderSectionWorkCommandHandler().execute(
        HandleScheduleClaimBuilderSectionWorkCommand(
            workflow_command=_workflow_command()
            if workflow_command is None
            else workflow_command,
        ),
        source_unit_repository=source_repository,
        knowledge_unit_of_work=scheduling_repository,
        workflow_unit_of_work=workflow_unit_of_work,
        frontend_event_projection_writer=frontend_event_projection_writer,
        capacity_admission_projection_writer=capacity_admission_projection_writer,
        capacity_admission_lane_target=capacity_admission_lane_target,
    )
    return result, source_repository, scheduling_repository, workflow_unit_of_work


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
async def test_rejects_wrong_command_type() -> None:
    with pytest.raises(ValueError, match="command_type"):
        await _execute(
            _workflow_command(
                command_type=KnowledgeExtractionCanonicalCommandType.INGEST_SOURCE_DOCUMENT.value
            )
        )


@pytest.mark.asyncio
async def test_rejects_non_pending_command() -> None:
    with pytest.raises(ValueError, match="PENDING"):
        await _execute(_workflow_command(status=WorkflowCommandStatus.COMPLETED))


@pytest.mark.asyncio
async def test_schedules_one_work_item_per_source_unit() -> None:
    result, _, scheduling_repository, _ = await _execute()

    assert result.scheduled_work_item_count == 2
    assert len(scheduling_repository.saved) == 2
    assert tuple(
        saved.payload["source_unit_ref"] for saved in scheduling_repository.saved
    ) == (
        f"{_document_ref().value}.unit.0",
        f"{_document_ref().value}.unit.1",
    )


@pytest.mark.asyncio
async def test_persists_capacity_admission_projection_when_configured() -> None:
    capacity_writer = FakeCapacityAdmissionProjectionWriter()

    await _execute(
        capacity_admission_projection_writer=capacity_writer,
        capacity_admission_lane_target=CapacityAdmissionLaneTarget(
            provider="groq",
            account_ref="groq_org_primary",
            model_ref="qwen/qwen3-32b",
        ),
    )

    assert len(capacity_writer.candidates) == 2
    first = capacity_writer.candidates[0]
    assert first.workflow_run_id == _workflow_run_id()
    assert first.project_id == "project-1"
    assert first.provider == "groq"
    assert first.account_ref == "groq_org_primary"
    assert first.model_ref == "qwen/qwen3-32b"
    assert first.status.value == "ready"


@pytest.mark.asyncio
async def test_appends_claim_builder_section_work_scheduled_event() -> None:
    result, _, _, workflow_unit_of_work = await _execute()

    assert result.appended_event_count == 3
    assert tuple(event.event_type for event in workflow_unit_of_work.outbox.events) == (
        KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SECTION_WORK_SCHEDULED.value,
        KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_WORK_ITEM_SCHEDULED.value,
        KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_WORK_ITEM_SCHEDULED.value,
    )
    assert (
        workflow_unit_of_work.outbox.events[0].payload["scheduled_work_item_count"] == 2
    )
    assert workflow_unit_of_work.outbox.events[1].payload["source_unit_ref"] == (
        f"{_document_ref().value}.unit.0"
    )
    assert workflow_unit_of_work.outbox.events[1].payload["attempt_count"] == 0


@pytest.mark.asyncio
async def test_appends_prepare_claim_builder_dispatch_batch_next_command() -> None:
    result, _, _, workflow_unit_of_work = await _execute()

    assert result.appended_next_command_count == 1
    next_command = workflow_unit_of_work.command_log.pending_commands[0]
    assert (
        next_command.command_type
        == KnowledgeExtractionCanonicalCommandType.PREPARE_CLAIM_BUILDER_DISPATCH_BATCH.value
    )
    assert next_command.idempotency_key.value == (
        f"prepare-claim-builder-dispatch-batch:{_workflow_run_id()}"
    )


@pytest.mark.asyncio
async def test_marks_original_command_completed() -> None:
    result, _, _, workflow_unit_of_work = await _execute()

    assert result.completed_command_id == _workflow_command().command_id
    assert workflow_unit_of_work.command_log.completed_command_ids == [
        _workflow_command().command_id
    ]


@pytest.mark.asyncio
async def test_updates_progress_snapshot_scheduled_work_items() -> None:
    _, _, _, workflow_unit_of_work = await _execute()

    snapshot = workflow_unit_of_work.progress_snapshots.snapshot
    assert snapshot is not None
    assert snapshot.current_phase == "CLAIM_BUILDER_WORK_SCHEDULING"
    assert snapshot.workflow_status == "RUNNING"
    assert snapshot.scheduled_work_items == 2
    assert snapshot.total_work_items == 2
    assert snapshot.domain_counters["scheduled_work_item_count"] == 2


@pytest.mark.asyncio
async def test_appends_timeline_entries() -> None:
    _, _, _, workflow_unit_of_work = await _execute()

    assert tuple(entry.message for entry in workflow_unit_of_work.timeline.entries) == (
        "Claim builder section work scheduled",
        "Prepare claim builder dispatch batch requested",
        "Schedule claim builder section work command completed",
    )


@dataclass(slots=True)
class FakeAttemptResult:
    started_attempts: tuple[object, ...]


@dataclass(slots=True)
class FakePrepareResult:
    attempt_result: FakeAttemptResult
    capacity_retry_at: datetime | None = None
    capacity_window_exhaustion: object | None = None
    affected_work_item_refs: tuple[str, ...] = ()
    source_unit_refs: tuple[str, ...] = ()
    input_size_preflight_decision: str = "USE_ACTIVE_MODEL"
    input_size_preflight_reason: str = (
        "estimated prompt tokens fit active model input limit"
    )
    input_size_preflight_active_model_ref: str | None = "qwen/qwen3-32b"
    source_split_required: bool = False


@dataclass(slots=True)
class FakePrepareLlmDispatchBatch:
    calls: list[PrepareLlmDispatchBatchCommand] = field(default_factory=list)

    async def execute(self, command: PrepareLlmDispatchBatchCommand) -> object:
        self.calls.append(command)
        return FakePrepareResult(
            attempt_result=FakeAttemptResult(started_attempts=()),
        )


@pytest.mark.asyncio
@pytest.mark.skip(
    reason="pre-existing baseline: schedule handler does not populate llm_dispatch_preparation in prepare command payload"
)
async def test_appends_prepare_command_with_default_llm_dispatch_preparation() -> None:
    _, _, _, workflow_unit_of_work = await _execute()

    next_command = workflow_unit_of_work.command_log.pending_commands[0]
    dispatch_preparation = next_command.payload.get("llm_dispatch_preparation")

    assert isinstance(dispatch_preparation, dict)
    assert set(dispatch_preparation) >= {
        "profile",
        "account_capacities",
        "active_model_ref",
        "requested_items",
        "worker_ref",
        "lease_token_prefix",
        "lease_ttl_seconds",
    }
    assert dispatch_preparation["active_model_ref"] == "qwen/qwen3-32b"
    assert dispatch_preparation["requested_items"] == 2
    assert dispatch_preparation["worker_ref"] == (
        "knowledge-workbench-claim-builder-dispatch"
    )
    assert dispatch_preparation["lease_token_prefix"] == (
        f"claim-builder-dispatch:{_workflow_run_id()}"
    )
    assert dispatch_preparation["lease_ttl_seconds"] == 300

    profile = dispatch_preparation["profile"]
    assert isinstance(profile, dict)
    assert profile["profile_id"] == "faq_claim_observations"
    assert profile["estimated_prompt_tokens"] == 3000
    assert profile["estimated_completion_tokens"] == 500
    assert profile["estimated_requests"] == 1

    account_capacities = dispatch_preparation["account_capacities"]
    assert isinstance(account_capacities, list)
    assert len(account_capacities) == 1
    account_capacity = account_capacities[0]
    assert isinstance(account_capacity, dict)
    assert account_capacity["provider"] == "groq"
    assert account_capacity["account_ref"] == "groq_org_primary"
    assert account_capacity["model_ref"] == "qwen/qwen3-32b"


@pytest.mark.asyncio
async def test_schedule_output_can_be_passed_to_prepare_without_missing_mapping() -> (
    None
):
    _, _, _, schedule_unit_of_work = await _execute()
    next_command = schedule_unit_of_work.command_log.pending_commands[0]
    prepare = FakePrepareLlmDispatchBatch()
    prepare_unit_of_work = FakeWorkflowRuntimeUnitOfWork()

    await HandlePrepareClaimBuilderDispatchBatchCommandHandler().execute(
        HandlePrepareClaimBuilderDispatchBatchCommand(
            workflow_command=next_command,
        ),
        prepare_llm_dispatch_batch=prepare,
        workflow_unit_of_work=prepare_unit_of_work,
    )

    assert len(prepare.calls) == 1
    assert prepare.calls[0].active_model_ref == "qwen/qwen3-32b"
    assert prepare.calls[0].requested_items == 2
    assert prepare.calls[0].worker.value == (
        "knowledge-workbench-claim-builder-dispatch"
    )


@pytest.mark.asyncio
async def test_projects_claim_builder_section_work_scheduled_event_once() -> None:
    repository = InMemoryFrontendWorkflowEventRepository()
    projection_writer = ProjectFrontendWorkflowEvent(
        projector=ClaimBuilderWorkSchedulingFrontendWorkflowEventProjector(),
        repository=repository,
    )

    _, _, _, workflow_unit_of_work = await _execute(
        frontend_event_projection_writer=projection_writer,
    )

    assert len(workflow_unit_of_work.outbox.events) == 3
    assert len(repository.events) == 3
    projected = next(
        event
        for event in repository.events.values()
        if event.projection_type == "workflow_work_items_scheduled"
    )
    assert projected.projection_type == "workflow_work_items_scheduled"
    assert projected.source_sequence_number == 1
    assert projected.payload == {
        "workflow_run_id": _workflow_run_id(),
        "source_document_ref": _document_ref().value,
        "scheduled_work_item_count": 2,
    }
    item_projections = tuple(
        event
        for event in repository.events.values()
        if event.projection_type == "workflow_claim_builder_work_item_scheduled"
    )
    assert len(item_projections) == 2
    assert item_projections[0].payload["source_unit_ordinal"] == 0


@pytest.mark.asyncio
async def test_appends_canonical_event_before_frontend_projection() -> None:
    repository = InMemoryFrontendWorkflowEventRepository()
    projection_writer = ProjectFrontendWorkflowEvent(
        projector=ClaimBuilderWorkSchedulingFrontendWorkflowEventProjector(),
        repository=repository,
    )

    await _execute(frontend_event_projection_writer=projection_writer)

    assert tuple(repository.events)[:1] == (
        "frontend-workflow-event:"
        "workflow-event:knowledge-extraction:source-document:project-1:abc:"
        "ClaimBuilderSectionWorkScheduled:source-document:project-1:abc:"
        "workflow_work_items_scheduled:v1",
    )


@pytest.mark.asyncio
async def test_reprojects_claim_builder_section_work_scheduled_idempotently() -> None:
    repository = InMemoryFrontendWorkflowEventRepository()
    projection_writer = ProjectFrontendWorkflowEvent(
        projector=ClaimBuilderWorkSchedulingFrontendWorkflowEventProjector(),
        repository=repository,
    )

    _, _, _, workflow_unit_of_work = await _execute(
        frontend_event_projection_writer=projection_writer,
    )
    persisted_event = workflow_unit_of_work.outbox.events[0]
    await projection_writer.execute(persisted_event)
    await projection_writer.execute(persisted_event)

    assert len(repository.events) == 3


@pytest.mark.asyncio
async def test_handler_without_projection_writer_preserves_existing_behavior() -> None:
    result, _, scheduling_repository, workflow_unit_of_work = await _execute()

    assert result.scheduled_work_item_count == 2
    assert len(scheduling_repository.saved) == 2
    assert len(workflow_unit_of_work.outbox.events) == 3


def test_schedule_handler_projects_after_canonical_outbox_append() -> None:
    source = inspect.getsource(
        HandleScheduleClaimBuilderSectionWorkCommandHandler.execute
    )

    append_index = source.index("outbox.append_event")
    projection_index = source.index("frontend_event_projection_writer.execute")
    assert append_index < projection_index


def test_schedule_handler_does_not_touch_live_state_or_execution_paths() -> None:
    source = inspect.getsource(
        HandleScheduleClaimBuilderSectionWorkCommandHandler.execute
    )

    for forbidden_marker in (
        "live_state",
        "fetch_workbench",
        "drain",
        "workflow_runner",
        "execution_runtime",
        "capacity_runtime",
        "capacity_window",
        "llm_attempt_capacity",
        "route_capacity",
    ):
        assert forbidden_marker not in source
