from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest

from src.contexts.capacity_runtime.application.ports.llm_attempt_capacity_observation_repository_port import (
    LlmAttemptCapacityObservation,
)
from src.contexts.execution_runtime.application.ports.work_item_attempt_dispatch_read_repository_port import (
    WorkItemAttemptDispatchForExecution,
)
from src.contexts.execution_runtime.application.use_cases.record_work_item_attempt_outcome import (
    RecordWorkItemAttemptOutcomeResult,
)
from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.value_objects.lease_token import LeaseToken
from src.contexts.execution_runtime.domain.value_objects.work_item_status import (
    WorkItemStatus,
)
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.knowledge_workbench.application.sagas.handle_execute_claim_builder_section_command import (
    HandleExecuteClaimBuilderSectionCommand,
    HandleExecuteClaimBuilderSectionCommandHandler,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalCommandType,
    KnowledgeExtractionCanonicalEventType,
)
from src.contexts.llm_runtime.application.ports.llm_dispatch_executor_port import (
    LlmDispatchExecutionResult,
    LlmDispatchExecutionStatus,
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
from src.interfaces.composition.execute_prepared_llm_dispatch_attempt import (
    ExecutePreparedLlmDispatchAttemptCommand,
    ExecutePreparedLlmDispatchAttemptResult,
)


def _now() -> datetime:
    return datetime(2026, 6, 11, 12, 0, tzinfo=UTC)


def _finished_at() -> datetime:
    return datetime(2026, 6, 11, 12, 1, tzinfo=UTC)


def _workflow_run_id() -> str:
    return "knowledge-extraction:source-document:project-1:abc"


def _attempt_id() -> str:
    return "work-1:attempt:1"


def _work_item_id() -> str:
    return "work-1"


def _capacity_payload() -> dict[str, object]:
    return {
        "provider": "groq",
        "account_ref": "groq_org_primary",
        "model_ref": "qwen/qwen3-32b",
        "remaining_minute_requests": 2,
        "remaining_minute_tokens": 7000,
        "remaining_daily_requests": 100,
        "remaining_daily_tokens": 50000,
        "minute_reset_at": _finished_at() + timedelta(seconds=60),
        "daily_reset_at": None,
        "actual_prompt_tokens": 10,
        "actual_completion_tokens": 5,
        "actual_total_tokens": 15,
        "outcome_class": "succeeded",
        "observed_at": _finished_at(),
    }


def _workflow_command(
    *,
    command_type: str = KnowledgeExtractionCanonicalCommandType.EXECUTE_CLAIM_BUILDER_SECTION.value,
    status: WorkflowCommandStatus = WorkflowCommandStatus.PENDING,
    workflow_run_id: str = _workflow_run_id(),
    payload_workflow_run_id: str | None = None,
) -> WorkflowCommand:
    return WorkflowCommand(
        command_id=WorkflowCommandId(
            f"workflow-command:execute-claim-builder-section:{workflow_run_id}:{_attempt_id()}"
        ),
        command_type=command_type,
        workflow_run_id=workflow_run_id,
        idempotency_key=WorkflowIdempotencyKey(
            f"execute-claim-builder-section:{workflow_run_id}:{_attempt_id()}"
        ),
        payload={
            "workflow_run_id": payload_workflow_run_id or workflow_run_id,
            "dispatch_attempt_id": _attempt_id(),
            "work_item_id": _work_item_id(),
        },
        status=status,
        run_after=_now(),
        created_at=_now(),
        updated_at=_now(),
    )


def _dispatch() -> WorkItemAttemptDispatchForExecution:
    return WorkItemAttemptDispatchForExecution(
        attempt_id=_attempt_id(),
        work_item_id=_work_item_id(),
        attempt_number=1,
        lease_token=LeaseToken("lease-token-1"),
        worker_ref="worker-1",
        dispatch_payload={
            "work_item_id": _work_item_id(),
            "schedule_payload": {"provider_messages": []},
            "llm_allocation": {
                "provider": "groq",
                "account_ref": "groq_org_primary",
                "model_ref": "qwen/qwen3-32b",
                "slot_index": 0,
            },
            "llm_execution_settings": {"reasoning_enabled": False},
        },
        started_at=_now(),
    )


def _execution_result(
    status: LlmDispatchExecutionStatus = LlmDispatchExecutionStatus.SUCCEEDED,
) -> ExecutePreparedLlmDispatchAttemptResult:
    if status is LlmDispatchExecutionStatus.SUCCEEDED:
        llm_result = LlmDispatchExecutionResult(
            status=status,
            finished_at=_finished_at(),
            output_payload={"raw_text": "{}"},
            capacity_observation=_capacity_payload(),
        )
        work_status = WorkItemStatus.COMPLETED
    elif status is LlmDispatchExecutionStatus.DEFERRED:
        llm_result = LlmDispatchExecutionResult(
            status=status,
            finished_at=_finished_at(),
            error_kind="minute_limit",
            next_attempt_at=_finished_at() + timedelta(minutes=1),
            capacity_observation={**_capacity_payload(), "outcome_class": status.value},
        )
        work_status = WorkItemStatus.DEFERRED
    else:
        llm_result = LlmDispatchExecutionResult(
            status=status,
            finished_at=_finished_at(),
            error_kind="provider_error",
            next_attempt_at=_finished_at() + timedelta(minutes=1)
            if status is LlmDispatchExecutionStatus.RETRYABLE_FAILED
            else None,
            capacity_observation={**_capacity_payload(), "outcome_class": status.value},
        )
        work_status = (
            WorkItemStatus.RETRYABLE_FAILED
            if status is LlmDispatchExecutionStatus.RETRYABLE_FAILED
            else WorkItemStatus.TERMINAL_FAILED
        )

    return ExecutePreparedLlmDispatchAttemptResult(
        dispatch=_dispatch(),
        llm_result=llm_result,
        outcome_result=RecordWorkItemAttemptOutcomeResult(
            work_item=WorkItem(
                work_item_id=_work_item_id(),
                work_kind=WorkKind(
                    "knowledge_workbench.claim_builder.section_extraction"
                ),
                status=work_status,
            )
        ),
    )


@dataclass(slots=True)
class FakeExecutePreparedLlmDispatchAttempt:
    result: ExecutePreparedLlmDispatchAttemptResult = field(
        default_factory=_execution_result,
    )
    calls: list[ExecutePreparedLlmDispatchAttemptCommand] = field(default_factory=list)

    async def execute(
        self, command: ExecutePreparedLlmDispatchAttemptCommand
    ) -> object:
        self.calls.append(command)
        return self.result


@dataclass(slots=True)
class FakeCapacityObservationRepository:
    observations: list[LlmAttemptCapacityObservation] = field(default_factory=list)

    async def record_observation(
        self,
        observation: LlmAttemptCapacityObservation,
    ) -> None:
        self.observations.append(observation)


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

    async def append_event(self, event: WorkflowEvent) -> WorkflowEvent:
        self.events.append(event)
        return event

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
        del workflow_run_id
        return self.snapshot

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
    *,
    workflow_command: WorkflowCommand | None = None,
    execution_result: ExecutePreparedLlmDispatchAttemptResult | None = None,
) -> tuple[
    object,
    FakeExecutePreparedLlmDispatchAttempt,
    FakeCapacityObservationRepository,
    FakeWorkflowRuntimeUnitOfWork,
]:
    executor = FakeExecutePreparedLlmDispatchAttempt(
        result=execution_result or _execution_result(),
    )
    capacity_repository = FakeCapacityObservationRepository()
    workflow_unit_of_work = FakeWorkflowRuntimeUnitOfWork()
    result = await HandleExecuteClaimBuilderSectionCommandHandler().execute(
        HandleExecuteClaimBuilderSectionCommand(
            workflow_command=workflow_command or _workflow_command(),
        ),
        execute_prepared_llm_dispatch_attempt=executor,
        capacity_observation_repository=capacity_repository,
        workflow_unit_of_work=workflow_unit_of_work,
    )
    return result, executor, capacity_repository, workflow_unit_of_work


@pytest.mark.asyncio
async def test_rejects_wrong_command_type() -> None:
    with pytest.raises(ValueError, match="command_type"):
        await _execute(
            workflow_command=_workflow_command(
                command_type=KnowledgeExtractionCanonicalCommandType.RECONCILE_CLAIM_BUILDER_PROGRESS.value,
            )
        )


@pytest.mark.asyncio
async def test_rejects_non_pending_command() -> None:
    with pytest.raises(ValueError, match="PENDING"):
        await _execute(
            workflow_command=_workflow_command(status=WorkflowCommandStatus.COMPLETED),
        )


@pytest.mark.asyncio
async def test_rejects_mismatched_workflow_run_id() -> None:
    with pytest.raises(ValueError, match="workflow_run_id"):
        await _execute(
            workflow_command=_workflow_command(
                payload_workflow_run_id="knowledge-extraction:other",
            )
        )


@pytest.mark.asyncio
async def test_calls_existing_execute_prepared_llm_dispatch_attempt() -> None:
    result, executor, _, _ = await _execute()

    assert result.dispatch_attempt_id == _attempt_id()
    assert result.work_item_id == _work_item_id()
    assert result.outcome_status == LlmDispatchExecutionStatus.SUCCEEDED.value
    assert executor.calls == [
        ExecutePreparedLlmDispatchAttemptCommand(attempt_id=_attempt_id())
    ]


@pytest.mark.asyncio
async def test_records_capacity_observation_feedback_contract() -> None:
    _, _, capacity_repository, _ = await _execute()

    assert len(capacity_repository.observations) == 1
    observation = capacity_repository.observations[0]
    assert observation.provider == "groq"
    assert observation.account_ref == "groq_org_primary"
    assert observation.model_ref == "qwen/qwen3-32b"
    assert observation.actual_total_tokens == 15


@pytest.mark.asyncio
async def test_appends_outcome_and_capacity_events() -> None:
    _, _, _, workflow_unit_of_work = await _execute()

    assert tuple(event.event_type for event in workflow_unit_of_work.outbox.events) == (
        KnowledgeExtractionCanonicalEventType.LLM_PROVIDER_CAPACITY_OBSERVED.value,
        KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SECTION_EXTRACTED.value,
    )
    outcome_event = workflow_unit_of_work.outbox.events[1]
    assert outcome_event.payload["dispatch_attempt_id"] == _attempt_id()
    assert outcome_event.payload["work_item_id"] == _work_item_id()
    assert outcome_event.payload["outcome_status"] == "succeeded"
    assert outcome_event.payload["actual_total_tokens"] == 15


@pytest.mark.asyncio
async def test_appends_reconcile_claim_builder_progress_command() -> None:
    _, _, _, workflow_unit_of_work = await _execute()

    assert tuple(
        command.command_type
        for command in workflow_unit_of_work.command_log.pending_commands
    ) == (
        KnowledgeExtractionCanonicalCommandType.RECONCILE_CLAIM_BUILDER_PROGRESS.value,
    )
    assert workflow_unit_of_work.command_log.pending_commands[
        0
    ].idempotency_key.value == (
        f"reconcile-claim-builder-progress:{_workflow_run_id()}:{_attempt_id()}"
    )


@pytest.mark.asyncio
async def test_marks_execute_claim_builder_section_completed() -> None:
    result, _, _, workflow_unit_of_work = await _execute()

    assert result.completed_command_id == _workflow_command().command_id
    assert workflow_unit_of_work.command_log.completed_command_ids == [
        _workflow_command().command_id,
    ]


@pytest.mark.asyncio
async def test_updates_progress_snapshot_and_timeline() -> None:
    _, _, _, workflow_unit_of_work = await _execute()

    snapshot = workflow_unit_of_work.progress_snapshots.snapshot
    assert snapshot is not None
    assert snapshot.current_phase == "CLAIM_BUILDER_SECTION_EXTRACTION"
    assert snapshot.completed_work_items == 1
    assert snapshot.domain_counters["executed_attempt_count"] == 1
    assert snapshot.domain_counters["capacity_observation_count"] == 1

    assert tuple(entry.message for entry in workflow_unit_of_work.timeline.entries) == (
        "Claim builder section attempt executed",
    )
    assert workflow_unit_of_work.timeline.entries[0].attempt_id == _attempt_id()


@pytest.mark.asyncio
async def test_deferred_outcome_updates_deferred_progress() -> None:
    _, _, _, workflow_unit_of_work = await _execute(
        execution_result=_execution_result(LlmDispatchExecutionStatus.DEFERRED),
    )

    snapshot = workflow_unit_of_work.progress_snapshots.snapshot
    assert snapshot is not None
    assert snapshot.deferred_work_items == 1
    assert workflow_unit_of_work.outbox.events[1].event_type == (
        KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SECTION_EXTRACTION_DEFERRED.value
    )
