from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta

import pytest

from src.contexts.knowledge_workbench.application.sagas.handle_prepare_claim_builder_dispatch_batch_command import (
    HandlePrepareClaimBuilderDispatchBatchCommand,
    HandlePrepareClaimBuilderDispatchBatchCommandHandler,
    HandlePrepareClaimBuilderDispatchBatchResult,
)
from src.contexts.execution_runtime.application.ports.work_item_lease_repository_port import (
    LeasedWorkItemRecord,
)
from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.value_objects.lease_token import LeaseToken
from src.contexts.execution_runtime.domain.value_objects.worker_ref import WorkerRef
from src.contexts.execution_runtime.domain.value_objects.work_item_status import (
    WorkItemStatus,
)
from src.contexts.knowledge_workbench.application.sagas.capacity_window_workflow_events import (
    CapacityWindowExhaustionSnapshot,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalCommandType,
    KnowledgeExtractionCanonicalEventType,
)
from src.contexts.knowledge_workbench.application.sagas.plan_claim_builder_section_work import (
    CLAIM_BUILDER_SECTION_WORK_KIND,
)
from src.contexts.knowledge_workbench.observability.application.models.frontend_workflow_event import (
    FrontendWorkflowEvent,
)
from src.contexts.knowledge_workbench.observability.application.projectors.claim_builder_dispatch_batch_frontend_workflow_event_projector import (
    ClaimBuilderDispatchBatchFrontendWorkflowEventProjector,
)
from src.contexts.knowledge_workbench.observability.application.projectors.project_frontend_workflow_event import (
    ProjectFrontendWorkflowEvent,
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
from src.contexts.llm_runtime.application.capacity.project_llm_capacity_to_capacity_runtime import (
    LlmCapacityAllocationSlot,
)
from src.contexts.llm_runtime.domain.capacity.llm_model_route_catalog import (
    default_groq_llm_model_route_catalog,
)
from src.interfaces.composition.lease_llm_admitted_work_items import (
    LlmAdmittedLeasedWorkItem,
)
from src.interfaces.composition.prepare_llm_dispatch_batch import (
    PrepareLlmDispatchBatchCommand,
)
from src.interfaces.composition.start_llm_admitted_work_item_attempts import (
    StartedLlmAdmittedAttempt,
)


def _now() -> datetime:
    return datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)


def _workflow_run_id() -> str:
    return "knowledge-extraction:source-document:project-1:abc"


def _dispatch_preparation() -> dict[str, object]:
    return {
        "profile": {
            "profile_id": "faq_claim_observations",
            "estimated_prompt_tokens": 3000,
            "estimated_completion_tokens": 500,
            "estimated_requests": 1,
        },
        "account_capacities": (
            {
                "provider": "groq",
                "account_ref": "groq_org_primary",
                "model_ref": "qwen/qwen3-32b",
                "remaining_minute_requests": 2,
                "remaining_minute_tokens": 7000,
                "remaining_daily_requests": 100,
                "remaining_daily_tokens": 50000,
            },
        ),
        "active_model_ref": "qwen/qwen3-32b",
        "requested_items": 2,
        "worker_ref": "worker-1",
        "lease_token_prefix": "lease-prefix",
        "lease_ttl_seconds": 300,
    }


def _workflow_command(
    *,
    command_type: str = (
        KnowledgeExtractionCanonicalCommandType.PREPARE_CLAIM_BUILDER_DISPATCH_BATCH.value
    ),
    status: WorkflowCommandStatus = WorkflowCommandStatus.PENDING,
) -> WorkflowCommand:
    return WorkflowCommand(
        command_id=WorkflowCommandId(
            f"workflow-command:prepare-claim-builder-dispatch-batch:{_workflow_run_id()}"
        ),
        command_type=command_type,
        workflow_run_id=_workflow_run_id(),
        idempotency_key=WorkflowIdempotencyKey(
            f"prepare-claim-builder-dispatch-batch:{_workflow_run_id()}"
        ),
        payload={
            "workflow_run_id": _workflow_run_id(),
            "source_document_ref": "source-document:project-1:abc",
            "scheduled_work_item_count": 2,
            "llm_dispatch_preparation": _dispatch_preparation(),
        },
        status=status,
        run_after=_now(),
        created_at=_now(),
        updated_at=_now(),
    )


def _workflow_command_with_malformed_dispatch_preparation() -> WorkflowCommand:
    command = _workflow_command()
    payload = dict(command.payload)
    payload["llm_dispatch_preparation"] = "not-a-mapping"
    return WorkflowCommand(
        command_id=command.command_id,
        command_type=command.command_type,
        workflow_run_id=command.workflow_run_id,
        idempotency_key=command.idempotency_key,
        payload=payload,
        status=command.status,
        run_after=command.run_after,
        created_at=command.created_at,
        updated_at=command.updated_at,
    )


def _attempt(index: int) -> StartedLlmAdmittedAttempt:
    return StartedLlmAdmittedAttempt(
        attempt_id=f"work-{index}:attempt:1",
        work_item_id=f"work-{index}",
        attempt_number=1,
        dispatch_payload={
            "work_item_id": f"work-{index}",
            "schedule_payload": {
                "source_document_ref": "source-document:project-1:abc",
                "source_unit_ref": f"unit-{index}",
            },
            "llm_allocation": {
                "provider": "groq",
                "account_ref": "groq_org_primary",
                "model_ref": "qwen/qwen3-32b",
            },
        },
    )


def _leased_item(
    attempt: StartedLlmAdmittedAttempt,
    *,
    selection_kind: str = "fresh",
) -> LlmAdmittedLeasedWorkItem:
    dispatch_payload = attempt.dispatch_payload
    allocation_mapping = dispatch_payload["llm_allocation"]
    assert isinstance(allocation_mapping, dict)
    route_catalog = default_groq_llm_model_route_catalog()
    model_ref = str(allocation_mapping["model_ref"])
    schedule_payload = dispatch_payload["schedule_payload"]
    assert isinstance(schedule_payload, dict)
    return LlmAdmittedLeasedWorkItem(
        leased=LeasedWorkItemRecord(
            work_item=WorkItem(
                work_item_id=attempt.work_item_id,
                work_kind=CLAIM_BUILDER_SECTION_WORK_KIND,
                status=WorkItemStatus.LEASED,
                attempt_count=1,
                leased_by=WorkerRef("worker-1"),
                lease_token=LeaseToken(f"lease:{attempt.work_item_id}"),
                lease_expires_at=_now(),
            ),
            schedule_payload=schedule_payload,
        ),
        allocation=LlmCapacityAllocationSlot(
            provider=str(allocation_mapping["provider"]),
            account_ref=str(allocation_mapping["account_ref"]),
            model_ref=model_ref,
            slot_index=0,
        ),
        execution_settings=route_catalog.execution_settings_for_model_ref(model_ref),
        selection_kind="retryable" if selection_kind == "retryable" else "fresh",
    )


@dataclass(slots=True)
class FakeLeaseResultWrapper:
    leased: tuple[LlmAdmittedLeasedWorkItem, ...]


@dataclass(slots=True)
class FakeAttemptResult:
    started_attempts: tuple[StartedLlmAdmittedAttempt, ...]


@dataclass(slots=True)
class FakePrepareResult:
    lease_result: FakeLeaseResultWrapper
    attempt_result: FakeAttemptResult
    affected_work_item_refs: tuple[str, ...] = ()
    source_unit_refs: tuple[str, ...] = ()
    input_size_preflight_decision: str = "USE_ACTIVE_MODEL"
    input_size_preflight_reason: str = (
        "estimated prompt tokens fit active model input limit"
    )
    input_size_preflight_active_model_ref: str | None = "qwen/qwen3-32b"
    source_split_required: bool = False
    capacity_retry_at: datetime | None = None
    capacity_window_exhaustion: CapacityWindowExhaustionSnapshot | None = None


@dataclass(slots=True)
class FakePrepareLlmDispatchBatch:
    started_attempts: tuple[StartedLlmAdmittedAttempt, ...] = field(
        default_factory=lambda: (_attempt(1), _attempt(2)),
    )
    affected_work_item_refs: tuple[str, ...] = ()
    source_unit_refs: tuple[str, ...] = ()
    input_size_preflight_decision: str = "USE_ACTIVE_MODEL"
    input_size_preflight_reason: str = (
        "estimated prompt tokens fit active model input limit"
    )
    input_size_preflight_active_model_ref: str | None = "qwen/qwen3-32b"
    source_split_required: bool = False
    capacity_retry_at: datetime | None = None
    capacity_window_exhaustion: CapacityWindowExhaustionSnapshot | None = None
    selection_kinds: tuple[str, ...] = ("fresh", "fresh")
    calls: list[PrepareLlmDispatchBatchCommand] = field(default_factory=list)

    async def execute(self, command: PrepareLlmDispatchBatchCommand) -> object:
        self.calls.append(command)
        leased_items = tuple(
            _leased_item(
                attempt,
                selection_kind=self.selection_kinds[index]
                if index < len(self.selection_kinds)
                else "fresh",
            )
            for index, attempt in enumerate(self.started_attempts)
        )
        return FakePrepareResult(
            lease_result=FakeLeaseResultWrapper(leased=leased_items),
            attempt_result=FakeAttemptResult(
                started_attempts=self.started_attempts,
            ),
            affected_work_item_refs=self.affected_work_item_refs,
            source_unit_refs=self.source_unit_refs,
            input_size_preflight_decision=self.input_size_preflight_decision,
            input_size_preflight_reason=self.input_size_preflight_reason,
            input_size_preflight_active_model_ref=(
                self.input_size_preflight_active_model_ref
            ),
            source_split_required=self.source_split_required,
            capacity_retry_at=self.capacity_retry_at,
            capacity_window_exhaustion=self.capacity_window_exhaustion,
        )


@dataclass(slots=True)
class FakeCommandLogRepository:
    pending_commands: list[WorkflowCommand] = field(default_factory=list)
    completed_command_ids: list[WorkflowCommandId] = field(default_factory=list)
    failed_command_ids: list[WorkflowCommandId] = field(default_factory=list)
    rescheduled_commands: list[tuple[WorkflowCommandId, datetime]] = field(
        default_factory=list,
    )

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

    async def mark_command_failed(
        self,
        *,
        command_id: WorkflowCommandId,
        failed_at: datetime,
    ) -> WorkflowCommand:
        del failed_at
        self.failed_command_ids.append(command_id)
        return _workflow_command(status=WorkflowCommandStatus.FAILED)

    async def reschedule_pending_command(
        self,
        *,
        command_id: WorkflowCommandId,
        run_after: datetime,
        rescheduled_at: datetime,
    ) -> WorkflowCommand:
        del rescheduled_at
        self.rescheduled_commands.append((command_id, run_after))
        return _workflow_command()

    async def list_pending_commands(
        self,
        *,
        workflow_run_id: str,
        limit: int,
    ) -> tuple[WorkflowCommand, ...]:
        del workflow_run_id
        return tuple(self.pending_commands[:limit])


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
        del workflow_run_id, limit
        return tuple(self.entries)


@dataclass(slots=True)
class FakeResourceUsageRepository:
    usage: WorkflowResourceUsageSnapshot | None = None

    async def get_usage(
        self,
        workflow_run_id: str,
    ) -> WorkflowResourceUsageSnapshot | None:
        del workflow_run_id
        return self.usage

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

    async def commit(self) -> None:
        raise AssertionError("handler must not own transaction commit")

    async def rollback(self) -> None:
        raise AssertionError("handler must not own transaction rollback")


async def _execute(
    workflow_command: WorkflowCommand | None = None,
    *,
    started_attempts: tuple[StartedLlmAdmittedAttempt, ...] | None = None,
    affected_work_item_refs: tuple[str, ...] = (),
    source_unit_refs: tuple[str, ...] = (),
    input_size_preflight_decision: str = "USE_ACTIVE_MODEL",
    input_size_preflight_reason: str = (
        "estimated prompt tokens fit active model input limit"
    ),
    input_size_preflight_active_model_ref: str | None = "qwen/qwen3-32b",
    source_split_required: bool = False,
    capacity_retry_at: datetime | None = None,
    capacity_window_exhaustion: CapacityWindowExhaustionSnapshot | None = None,
    selection_kinds: tuple[str, ...] = ("fresh", "fresh"),
    frontend_event_projection_writer: ProjectFrontendWorkflowEvent | None = None,
) -> tuple[
    HandlePrepareClaimBuilderDispatchBatchResult,
    FakePrepareLlmDispatchBatch,
    FakeWorkflowRuntimeUnitOfWork,
]:
    prepare = FakePrepareLlmDispatchBatch(
        started_attempts=(_attempt(1), _attempt(2))
        if started_attempts is None
        else started_attempts,
        affected_work_item_refs=affected_work_item_refs,
        source_unit_refs=source_unit_refs,
        input_size_preflight_decision=input_size_preflight_decision,
        input_size_preflight_reason=input_size_preflight_reason,
        input_size_preflight_active_model_ref=input_size_preflight_active_model_ref,
        source_split_required=source_split_required,
        capacity_retry_at=capacity_retry_at,
        capacity_window_exhaustion=capacity_window_exhaustion,
        selection_kinds=selection_kinds,
    )
    workflow_unit_of_work = FakeWorkflowRuntimeUnitOfWork()
    result = await HandlePrepareClaimBuilderDispatchBatchCommandHandler().execute(
        HandlePrepareClaimBuilderDispatchBatchCommand(
            workflow_command=_workflow_command()
            if workflow_command is None
            else workflow_command,
        ),
        prepare_llm_dispatch_batch=prepare,
        workflow_unit_of_work=workflow_unit_of_work,
        frontend_event_projection_writer=frontend_event_projection_writer,
    )
    return result, prepare, workflow_unit_of_work


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
                command_type=KnowledgeExtractionCanonicalCommandType.INGEST_SOURCE_DOCUMENT.value,
            ),
        )


@pytest.mark.asyncio
async def test_rejects_non_pending_command() -> None:
    with pytest.raises(ValueError, match="PENDING"):
        await _execute(
            _workflow_command(status=WorkflowCommandStatus.COMPLETED),
        )


@pytest.mark.asyncio
async def test_calls_existing_prepare_llm_dispatch_batch_for_claim_builder_work_kind() -> (
    None
):
    result, prepare, _ = await _execute()

    assert result.prepared_dispatch_count == 2
    assert len(prepare.calls) == 1
    assert prepare.calls[0].work_kind == CLAIM_BUILDER_SECTION_WORK_KIND
    assert prepare.calls[0].active_model_ref == "qwen/qwen3-32b"
    assert prepare.calls[0].requested_items == 2
    assert prepare.calls[0].profile is not None
    assert prepare.calls[0].profile.profile_id == "faq_claim_observations"
    assert len(prepare.calls[0].account_capacities) == 1
    assert prepare.calls[0].now > _workflow_command().updated_at
    assert prepare.calls[0].started_at == prepare.calls[0].now
    assert prepare.calls[0].lease_expires_at == (
        prepare.calls[0].now + timedelta(seconds=90)
    )


@pytest.mark.asyncio
async def test_reads_target_profile_keys_from_llm_dispatch_preparation() -> None:
    workflow_command = _workflow_command()
    payload = dict(workflow_command.payload)
    dispatch_preparation = payload["llm_dispatch_preparation"]
    assert isinstance(dispatch_preparation, dict)
    dispatch_preparation = dict(dispatch_preparation)
    profile = dispatch_preparation["profile"]
    assert isinstance(profile, dict)
    profile = dict(profile)
    profile.pop("estimated_prompt_tokens")
    profile.pop("estimated_completion_tokens")
    profile["estimated_input_tokens"] = 3456
    profile["estimated_output_tokens"] = 789
    dispatch_preparation["profile"] = profile
    payload["llm_dispatch_preparation"] = dispatch_preparation
    workflow_command = WorkflowCommand(
        command_id=workflow_command.command_id,
        command_type=workflow_command.command_type,
        workflow_run_id=workflow_command.workflow_run_id,
        idempotency_key=workflow_command.idempotency_key,
        payload=payload,
        status=workflow_command.status,
        run_after=workflow_command.run_after,
        created_at=workflow_command.created_at,
        updated_at=workflow_command.updated_at,
    )

    _, prepare, _ = await _execute(workflow_command)

    assert prepare.calls[0].profile is not None
    assert prepare.calls[0].profile.estimated_input_tokens == 3456
    assert prepare.calls[0].profile.estimated_output_tokens == 789


@pytest.mark.asyncio
async def test_appends_claim_builder_dispatch_batch_prepared_event() -> None:
    result, _, workflow_unit_of_work = await _execute()

    assert result.appended_event_count == 5
    event = workflow_unit_of_work.outbox.events[0]
    assert (
        event.event_type
        == KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_DISPATCH_BATCH_PREPARED.value
    )
    assert event.payload["workflow_run_id"] == _workflow_run_id()
    assert event.payload["work_kind"] == CLAIM_BUILDER_SECTION_WORK_KIND.value
    assert event.payload["prepared_dispatch_count"] == 2
    assert event.payload["dispatch_attempt_ids"] == (
        "work-1:attempt:1",
        "work-2:attempt:1",
    )
    assert event.payload["work_item_ids"] == ("work-1", "work-2")
    assert tuple(
        event.event_type for event in workflow_unit_of_work.outbox.events[1:]
    ) == (
        KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_DISPATCH_ATTEMPT_PREPARED.value,
        KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_DISPATCH_ATTEMPT_PREPARED.value,
        KnowledgeExtractionCanonicalEventType.CAPACITY_WINDOW_LEASED_WORK_ITEM.value,
        KnowledgeExtractionCanonicalEventType.CAPACITY_WINDOW_LEASED_WORK_ITEM.value,
    )
    assert workflow_unit_of_work.outbox.events[1].payload["source_unit_ref"] == "unit-1"
    assert (
        workflow_unit_of_work.outbox.events[1].payload["dispatch_attempt_id"]
        == "work-1:attempt:1"
    )


@pytest.mark.asyncio
async def test_appends_execute_claim_builder_section_per_prepared_attempt() -> None:
    result, _, workflow_unit_of_work = await _execute()

    assert result.appended_next_command_count == 2
    assert tuple(
        command.command_type
        for command in workflow_unit_of_work.command_log.pending_commands
    ) == (
        KnowledgeExtractionCanonicalCommandType.EXECUTE_CLAIM_BUILDER_SECTION.value,
        KnowledgeExtractionCanonicalCommandType.EXECUTE_CLAIM_BUILDER_SECTION.value,
    )
    assert tuple(
        command.idempotency_key.value
        for command in workflow_unit_of_work.command_log.pending_commands
    ) == (
        f"execute-claim-builder-section:{_workflow_run_id()}:work-1:attempt:1",
        f"execute-claim-builder-section:{_workflow_run_id()}:work-2:attempt:1",
    )


@pytest.mark.asyncio
async def test_execute_commands_include_claim_builder_prepare_origin_trace() -> None:
    _, _, workflow_unit_of_work = await _execute()
    prepare_command = _workflow_command()

    for command in workflow_unit_of_work.command_log.pending_commands:
        assert command.payload["claim_builder_prepare_command_id"] == (
            prepare_command.command_id.value
        )
        assert command.payload["claim_builder_prepare_idempotency_key"] == (
            prepare_command.idempotency_key.value
        )


@pytest.mark.asyncio
async def test_marks_prepare_completed_when_scheduled_work_has_no_due_items() -> None:
    result, _, workflow_unit_of_work = await _execute(started_attempts=())

    assert result.prepared_dispatch_count == 0
    assert result.appended_event_count == 0
    assert result.appended_next_command_count == 0
    assert workflow_unit_of_work.outbox.events == []
    assert workflow_unit_of_work.command_log.pending_commands == []
    assert workflow_unit_of_work.command_log.failed_command_ids == []
    assert workflow_unit_of_work.command_log.completed_command_ids == [
        _workflow_command().command_id,
    ]

    assert tuple(entry.message for entry in workflow_unit_of_work.timeline.entries) == (
        "Claim builder dispatch batch prepared zero attempts after scheduled work items",
    )
    entry = workflow_unit_of_work.timeline.entries[0]
    assert entry.event_type == "ClaimBuilderDispatchBatchPreparedZero"
    assert entry.severity.value == "INFO"
    assert entry.payload_summary["scheduled_work_item_count"] == 2
    assert entry.payload_summary["prepared_dispatch_count"] == 0


@pytest.mark.asyncio
async def test_reschedules_prepare_when_zero_attempts_are_capacity_throttled() -> None:
    retry_at = datetime.now(timezone.utc) + timedelta(seconds=60)
    exhaustion = CapacityWindowExhaustionSnapshot(
        provider="groq",
        account_ref="groq_org_primary",
        model_ref="qwen/qwen3-32b",
        exhausted_reason="prepare_capacity_window_unavailable",
        exhausted_dimensions=("minute_tokens",),
        reset_at=retry_at,
    )

    result, _, workflow_unit_of_work = await _execute(
        started_attempts=(),
        capacity_retry_at=retry_at,
        capacity_window_exhaustion=exhaustion,
    )

    assert result.prepared_dispatch_count == 0
    assert result.appended_event_count == 1
    assert result.appended_next_command_count == 0
    assert workflow_unit_of_work.command_log.failed_command_ids == []
    assert workflow_unit_of_work.command_log.completed_command_ids == []
    assert workflow_unit_of_work.command_log.rescheduled_commands == [
        (_workflow_command().command_id, retry_at),
    ]
    assert tuple(entry.message for entry in workflow_unit_of_work.timeline.entries) == (
        "Claim builder dispatch capacity temporarily unavailable",
    )


@pytest.mark.asyncio
async def test_capacity_retry_at_in_past_is_clamped_to_future() -> None:
    stale_retry_at = _now() + timedelta(seconds=60)

    result, _, workflow_unit_of_work = await _execute(
        started_attempts=(),
        capacity_retry_at=stale_retry_at,
    )

    assert result.prepared_dispatch_count == 0
    assert workflow_unit_of_work.command_log.rescheduled_commands
    _, run_after = workflow_unit_of_work.command_log.rescheduled_commands[0]
    assert run_after > datetime.now(timezone.utc)
    assert run_after != stale_retry_at


@pytest.mark.asyncio
async def test_marks_prepare_claim_builder_dispatch_batch_completed() -> None:
    result, _, workflow_unit_of_work = await _execute()

    assert result.completed_command_id == _workflow_command().command_id
    assert workflow_unit_of_work.command_log.completed_command_ids == [
        _workflow_command().command_id,
    ]


@pytest.mark.asyncio
async def test_updates_progress_and_timeline() -> None:
    _, _, workflow_unit_of_work = await _execute()

    snapshot = workflow_unit_of_work.progress_snapshots.snapshot
    assert snapshot is not None
    assert snapshot.current_phase == "CLAIM_BUILDER_SECTION_EXTRACTION"
    assert snapshot.workflow_status == "RUNNING"
    assert snapshot.running_work_items == 2
    assert snapshot.domain_counters["prepared_dispatch_count"] == 2

    assert tuple(entry.message for entry in workflow_unit_of_work.timeline.entries) == (
        "Claim builder dispatch batch prepared",
        "Execute claim builder section requested",
    )


@pytest.mark.asyncio
async def test_forwards_llm_dispatch_preparation_strategy_to_prepare_command() -> None:
    workflow_command = _workflow_command()
    payload = dict(workflow_command.payload)
    payload["llm_dispatch_preparation_strategy"] = "FALLBACK_MODEL_REQUIRED"
    workflow_command = WorkflowCommand(
        command_id=workflow_command.command_id,
        command_type=workflow_command.command_type,
        workflow_run_id=workflow_command.workflow_run_id,
        idempotency_key=workflow_command.idempotency_key,
        payload=payload,
        status=workflow_command.status,
        run_after=workflow_command.run_after,
        created_at=workflow_command.created_at,
        updated_at=workflow_command.updated_at,
    )

    _, prepare, _ = await _execute(workflow_command)

    assert prepare.calls[0].dispatch_preparation_strategy == ("FALLBACK_MODEL_REQUIRED")


@pytest.mark.asyncio
async def test_forwards_reconcile_produced_fallback_strategy_marker() -> None:
    workflow_command = _workflow_command()
    payload = dict(workflow_command.payload)
    payload["selected_retry_strategy"] = "FALLBACK_MODEL_REQUIRED"
    workflow_command = WorkflowCommand(
        command_id=workflow_command.command_id,
        command_type=workflow_command.command_type,
        workflow_run_id=workflow_command.workflow_run_id,
        idempotency_key=workflow_command.idempotency_key,
        payload=payload,
        status=workflow_command.status,
        run_after=workflow_command.run_after,
        created_at=workflow_command.created_at,
        updated_at=workflow_command.updated_at,
    )

    _, prepare, _ = await _execute(workflow_command)

    assert prepare.calls[0].dispatch_preparation_strategy == ("FALLBACK_MODEL_REQUIRED")


@pytest.mark.asyncio
async def test_prepare_event_exposes_input_size_preflight_metadata() -> None:
    _, _, workflow_unit_of_work = await _execute(
        input_size_preflight_decision="USE_LARGER_INPUT_MODEL",
        input_size_preflight_reason=(
            "estimated prompt tokens exceed active model input limit; "
            "selected larger input model"
        ),
        input_size_preflight_active_model_ref="openai/gpt-oss-120b",
    )

    event = workflow_unit_of_work.outbox.events[0]
    assert event.payload["input_size_preflight_decision"] == ("USE_LARGER_INPUT_MODEL")
    assert event.payload["input_size_preflight_active_model_ref"] == (
        "openai/gpt-oss-120b"
    )
    snapshot = workflow_unit_of_work.progress_snapshots.snapshot
    assert snapshot is not None
    assert (
        snapshot.domain_counters["input_size_preflight_larger_input_model_count"] == 1
    )


@pytest.mark.asyncio
async def test_source_split_required_prepare_result_emits_split_command() -> None:
    result, _, workflow_unit_of_work = await _execute(
        started_attempts=(),
        input_size_preflight_decision="SOURCE_SPLIT_REQUIRED",
        input_size_preflight_reason=(
            "estimated prompt tokens exceed all automatic fallback input limits"
        ),
        input_size_preflight_active_model_ref="qwen/qwen3-32b",
        affected_work_item_refs=("work-1",),
        source_unit_refs=("unit-1",),
        source_split_required=True,
    )

    assert result.prepared_dispatch_count == 0
    assert result.appended_event_count == 1
    assert result.appended_next_command_count == 1
    assert tuple(
        command.command_type
        for command in workflow_unit_of_work.command_log.pending_commands
    ) == (
        KnowledgeExtractionCanonicalCommandType.SPLIT_CLAIM_BUILDER_SOURCE_UNIT.value,
    )
    event = workflow_unit_of_work.outbox.events[0]
    assert event.payload["source_split_required"] is True
    assert event.payload["input_size_preflight_decision"] == "SOURCE_SPLIT_REQUIRED"
    snapshot = workflow_unit_of_work.progress_snapshots.snapshot
    assert snapshot is not None
    assert (
        snapshot.domain_counters["input_size_preflight_source_split_required_count"]
        == 1
    )


@pytest.mark.asyncio
async def test_source_split_required_emits_split_required_event_and_command() -> None:
    result, _, workflow_unit_of_work = await _execute(
        started_attempts=(),
        input_size_preflight_decision="SOURCE_SPLIT_REQUIRED",
        input_size_preflight_reason=(
            "estimated prompt tokens exceed all automatic fallback input limits"
        ),
        input_size_preflight_active_model_ref="qwen/qwen3-32b",
        affected_work_item_refs=("work-1",),
        source_unit_refs=("unit-1",),
        source_split_required=True,
    )

    assert result.appended_event_count == 1
    assert result.appended_next_command_count == 1

    event = workflow_unit_of_work.outbox.events[0]
    assert (
        event.event_type
        == KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SOURCE_UNIT_SPLIT_REQUIRED.value
    )
    assert (
        event.event_type
        != KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_DISPATCH_BATCH_PREPARED.value
    )

    command = workflow_unit_of_work.command_log.pending_commands[0]
    assert (
        command.command_type
        == KnowledgeExtractionCanonicalCommandType.SPLIT_CLAIM_BUILDER_SOURCE_UNIT.value
    )
    assert command.payload["workflow_run_id"] == _workflow_run_id()
    assert command.payload["source_document_ref"] == "source-document:project-1:abc"
    assert command.payload["source_unit_ref"] == "unit-1"
    assert command.payload["source_unit_refs"] == ("unit-1",)
    assert command.payload["affected_work_item_refs"] == ("work-1",)
    assert command.payload["estimated_input_tokens"] == 3000
    assert command.payload["estimated_prompt_tokens"] == 3000
    assert command.payload["active_model_ref"] == "qwen/qwen3-32b"
    assert command.payload["input_size_preflight_decision"] == ("SOURCE_SPLIT_REQUIRED")
    assert command.payload["input_size_preflight_reason"] == (
        "estimated prompt tokens exceed all automatic fallback input limits"
    )
    assert event.payload["source_split_required"] is True
    assert event.payload["source_unit_refs"] == ("unit-1",)
    assert event.payload["affected_work_item_refs"] == ("work-1",)
    assert event.payload["split_reason"] == "input_size_preflight"
    assert ("split_handler_" + "status") not in event.payload
    assert ("BLOCKED_" + "NOT_IMPLEMENTED") not in str(event.payload)

    assert command.payload["source_split_required"] is True
    assert command.payload["source_unit_refs"] == ("unit-1",)
    assert command.payload["affected_work_item_refs"] == ("work-1",)
    assert command.payload["split_reason"] == "input_size_preflight"
    assert ("split_handler_" + "status") not in command.payload
    assert ("BLOCKED_" + "NOT_IMPLEMENTED") not in str(command.payload)


@pytest.mark.asyncio
async def test_source_split_required_records_progress_and_timeline() -> None:
    _, _, workflow_unit_of_work = await _execute(
        started_attempts=(),
        input_size_preflight_decision="SOURCE_SPLIT_REQUIRED",
        input_size_preflight_reason=(
            "estimated prompt tokens exceed all automatic fallback input limits"
        ),
        input_size_preflight_active_model_ref="qwen/qwen3-32b",
        affected_work_item_refs=("work-1",),
        source_unit_refs=("unit-1",),
        source_split_required=True,
    )

    snapshot = workflow_unit_of_work.progress_snapshots.snapshot
    assert snapshot is not None
    assert snapshot.domain_counters["claim_builder_source_split_required_count"] == 1
    assert (
        snapshot.domain_counters["input_size_preflight_source_split_required_count"]
        == 1
    )

    assert tuple(entry.message for entry in workflow_unit_of_work.timeline.entries) == (
        "Claim builder source unit split required",
    )


@pytest.mark.asyncio
async def test_source_split_required_does_not_emit_dispatch_prepared_or_execute_commands() -> (
    None
):
    _, _, workflow_unit_of_work = await _execute(
        started_attempts=(),
        input_size_preflight_decision="SOURCE_SPLIT_REQUIRED",
        input_size_preflight_reason=(
            "estimated prompt tokens exceed all automatic fallback input limits"
        ),
        input_size_preflight_active_model_ref="qwen/qwen3-32b",
        affected_work_item_refs=("work-1",),
        source_unit_refs=("unit-1",),
        source_split_required=True,
    )

    assert all(
        event.event_type
        != KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_DISPATCH_BATCH_PREPARED.value
        for event in workflow_unit_of_work.outbox.events
    )
    assert tuple(
        command.command_type
        for command in workflow_unit_of_work.command_log.pending_commands
    ) == (
        KnowledgeExtractionCanonicalCommandType.SPLIT_CLAIM_BUILDER_SOURCE_UNIT.value,
    )


@pytest.mark.asyncio
async def test_source_split_required_raises_when_prepare_result_has_no_source_unit_ref() -> (
    None
):
    with pytest.raises(ValueError, match="source_unit_refs"):
        await _execute(
            started_attempts=(),
            input_size_preflight_decision="SOURCE_SPLIT_REQUIRED",
            input_size_preflight_reason=(
                "estimated prompt tokens exceed all automatic fallback input limits"
            ),
            input_size_preflight_active_model_ref="qwen/qwen3-32b",
            affected_work_item_refs=("work-1",),
            source_unit_refs=(),
            source_split_required=True,
        )


@pytest.mark.asyncio
async def test_rejects_malformed_explicit_llm_dispatch_preparation() -> None:
    with pytest.raises(ValueError, match="llm_dispatch_preparation"):
        await _execute(_workflow_command_with_malformed_dispatch_preparation())


@pytest.mark.asyncio
async def test_projects_claim_builder_dispatch_batch_prepared_event_once() -> None:
    repository = InMemoryFrontendWorkflowEventRepository()
    projection_writer = ProjectFrontendWorkflowEvent(
        projector=ClaimBuilderDispatchBatchFrontendWorkflowEventProjector(),
        repository=repository,
    )

    _, _, workflow_unit_of_work = await _execute(
        frontend_event_projection_writer=projection_writer,
    )

    assert len(workflow_unit_of_work.outbox.events) == 5
    assert len(repository.events) == 3
    projected = next(
        event
        for event in repository.events.values()
        if event.projection_type == "workflow_dispatch_batch_prepared"
    )
    assert projected.projection_type == "workflow_dispatch_batch_prepared"
    assert projected.payload["prepared_dispatch_count"] == 2
    attempt_projections = tuple(
        event
        for event in repository.events.values()
        if event.projection_type == "workflow_claim_builder_dispatch_attempt_prepared"
    )
    assert len(attempt_projections) == 2
    assert attempt_projections[0].payload["provider"] == "groq"


@pytest.mark.asyncio
async def test_reprojects_dispatch_batch_prepared_idempotently() -> None:
    repository = InMemoryFrontendWorkflowEventRepository()
    projection_writer = ProjectFrontendWorkflowEvent(
        projector=ClaimBuilderDispatchBatchFrontendWorkflowEventProjector(),
        repository=repository,
    )

    _, _, workflow_unit_of_work = await _execute(
        frontend_event_projection_writer=projection_writer,
    )
    persisted_event = workflow_unit_of_work.outbox.events[0]
    await projection_writer.execute(persisted_event)
    await projection_writer.execute(persisted_event)

    assert len(repository.events) == 3


@pytest.mark.asyncio
async def test_zero_dispatch_path_does_not_create_dispatch_prepared_projection() -> (
    None
):
    repository = InMemoryFrontendWorkflowEventRepository()
    projection_writer = ProjectFrontendWorkflowEvent(
        projector=ClaimBuilderDispatchBatchFrontendWorkflowEventProjector(),
        repository=repository,
    )

    await _execute(
        started_attempts=(),
        frontend_event_projection_writer=projection_writer,
    )

    assert repository.events == {}


@pytest.mark.asyncio
async def test_source_split_required_path_does_not_create_dispatch_prepared_projection() -> (
    None
):
    repository = InMemoryFrontendWorkflowEventRepository()
    projection_writer = ProjectFrontendWorkflowEvent(
        projector=ClaimBuilderDispatchBatchFrontendWorkflowEventProjector(),
        repository=repository,
    )

    await _execute(
        started_attempts=(),
        input_size_preflight_decision="SOURCE_SPLIT_REQUIRED",
        input_size_preflight_reason=(
            "estimated prompt tokens exceed all automatic fallback input limits"
        ),
        input_size_preflight_active_model_ref="qwen/qwen3-32b",
        affected_work_item_refs=("work-1",),
        source_unit_refs=("unit-1",),
        source_split_required=True,
        frontend_event_projection_writer=projection_writer,
    )

    assert all(
        event.projection_type != "workflow_dispatch_batch_prepared"
        for event in repository.events.values()
    )
    assert repository.events == {}


@pytest.mark.asyncio
async def test_handler_without_projection_writer_preserves_existing_behavior() -> None:
    result, _, workflow_unit_of_work = await _execute()

    assert result.prepared_dispatch_count == 2
    assert len(workflow_unit_of_work.outbox.events) == 5


def test_prepare_handler_projects_after_canonical_outbox_append() -> None:
    source = inspect.getsource(
        HandlePrepareClaimBuilderDispatchBatchCommandHandler.execute
    )

    append_index = source.index("outbox.append_event")
    projection_index = source.index("frontend_event_projection_writer.execute")
    assert append_index < projection_index


def test_prepare_handler_does_not_touch_live_state_or_execution_paths() -> None:
    source = inspect.getsource(
        HandlePrepareClaimBuilderDispatchBatchCommandHandler.execute
    )

    for forbidden_marker in (
        "live_state",
        "fetch_workbench",
        "drain",
        "workflow_runner",
        "frontend_workflow_events",
    ):
        assert forbidden_marker not in source


@pytest.mark.asyncio
async def test_emits_capacity_window_leased_with_selection_kind_per_item() -> None:
    _, _, workflow_unit_of_work = await _execute(
        selection_kinds=("fresh", "retryable"),
    )

    leased_events = [
        event
        for event in workflow_unit_of_work.outbox.events
        if event.event_type
        == KnowledgeExtractionCanonicalEventType.CAPACITY_WINDOW_LEASED_WORK_ITEM.value
    ]
    assert len(leased_events) == 2
    assert leased_events[0].payload["selection_kind"] == "fresh"
    assert leased_events[1].payload["selection_kind"] == "retryable"
    assert leased_events[0].payload["window_key"] == (
        "groq:groq_org_primary:qwen/qwen3-32b"
    )
    assert leased_events[0].payload["lease_expires_at"]
    assert "next_attempt_at" not in leased_events[0].payload
    assert "retry_owner" not in leased_events[0].payload


@pytest.mark.asyncio
async def test_zero_dispatch_without_capacity_exhaustion_does_not_emit_exhausted() -> (
    None
):
    _, _, workflow_unit_of_work = await _execute(started_attempts=())

    exhausted_events = [
        event
        for event in workflow_unit_of_work.outbox.events
        if event.event_type
        == KnowledgeExtractionCanonicalEventType.CAPACITY_WINDOW_EXHAUSTED.value
    ]
    assert exhausted_events == []


@pytest.mark.asyncio
async def test_capacity_throttled_zero_dispatch_emits_capacity_window_exhausted() -> (
    None
):
    retry_at = datetime.now(timezone.utc) + timedelta(seconds=60)
    exhaustion = CapacityWindowExhaustionSnapshot(
        provider="groq",
        account_ref="groq_org_primary",
        model_ref="qwen/qwen3-32b",
        exhausted_reason="prepare_capacity_window_unavailable",
        exhausted_dimensions=("minute_tokens",),
        reset_at=retry_at,
    )

    _, _, workflow_unit_of_work = await _execute(
        started_attempts=(),
        capacity_retry_at=retry_at,
        capacity_window_exhaustion=exhaustion,
    )

    exhausted_events = [
        event
        for event in workflow_unit_of_work.outbox.events
        if event.event_type
        == KnowledgeExtractionCanonicalEventType.CAPACITY_WINDOW_EXHAUSTED.value
    ]
    assert len(exhausted_events) == 1
    payload = exhausted_events[0].payload
    assert payload["reset_at"] == retry_at.isoformat()
    assert payload["exhausted_dimensions"] == ["minute_tokens"]
    assert "next_attempt_at" not in payload
    assert "retry_owner" not in payload
    assert "work_item_retry_timer" not in payload
