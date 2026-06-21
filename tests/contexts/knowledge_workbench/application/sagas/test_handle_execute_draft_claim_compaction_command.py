from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import inspect

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
from src.contexts.execution_runtime.domain.value_objects.lease_token import LeaseToken
from src.contexts.knowledge_workbench.application.sagas.handle_execute_draft_claim_compaction_command import (
    DraftClaimCompactionLlmDispatchOutputValidator,
    HandleExecuteDraftClaimCompactionCommand,
    HandleExecuteDraftClaimCompactionCommandHandler,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalCommandType,
    KnowledgeExtractionCanonicalEventType,
    KnowledgeExtractionCanonicalPhase,
)
from src.contexts.knowledge_workbench.observability.application.models.frontend_workflow_event import (
    FrontendWorkflowEvent,
)
from src.contexts.knowledge_workbench.observability.application.projectors.llm_provider_capacity_observed_frontend_workflow_event_projector import (
    LlmProviderCapacityObservedFrontendWorkflowEventProjector,
)
from src.contexts.knowledge_workbench.observability.application.projectors.project_frontend_workflow_event import (
    ProjectFrontendWorkflowEvent,
)
from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_attempt_input import (
    DraftClaimCompactionExpectedOutputKind,
)
from src.contexts.knowledge_workbench.extraction.application.policies.draft_claim_compaction_output_validator import (
    DraftClaimCompactionOutputValidator,
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
    return datetime(2026, 6, 14, 12, 0, tzinfo=timezone.utc)


def _workflow_run_id() -> str:
    return "workflow-1"


def _command(
    *,
    expected_output_kind: str = "compacted_claims",
    source_node_refs: tuple[str, ...] = (),
    status: WorkflowCommandStatus = WorkflowCommandStatus.PENDING,
) -> WorkflowCommand:
    payload: dict[str, object] = {
        "workflow_run_id": _workflow_run_id(),
        "dispatch_attempt_id": "attempt-1",
        "work_item_id": "work-item-1",
        "group_ref": "group-1",
        "batch_ref": "batch-1",
        "round_index": 0,
        "expected_output_kind": expected_output_kind,
        "source_claim_refs": ["claim-a", "claim-b"],
        "source_node_refs": list(source_node_refs),
    }
    return WorkflowCommand(
        command_id=WorkflowCommandId("workflow-command:ExecuteDraftClaimCompaction"),
        command_type=KnowledgeExtractionCanonicalCommandType.EXECUTE_DRAFT_CLAIM_COMPACTION.value,
        workflow_run_id=_workflow_run_id(),
        idempotency_key=WorkflowIdempotencyKey(
            "ExecuteDraftClaimCompaction:workflow-1"
        ),
        payload=payload,
        status=status,
        run_after=_now(),
        created_at=_now(),
        updated_at=_now(),
    )


@dataclass(slots=True)
class FakeCapacityObservationRepository:
    observations: list[LlmAttemptCapacityObservation] = field(default_factory=list)

    async def record_observation(
        self,
        observation: LlmAttemptCapacityObservation,
    ) -> None:
        self.observations.append(observation)


@dataclass(slots=True)
class FakeExecutePreparedDispatchAttempt:
    result: ExecutePreparedLlmDispatchAttemptResult
    calls: list[ExecutePreparedLlmDispatchAttemptCommand] = field(default_factory=list)

    async def execute(
        self,
        command: ExecutePreparedLlmDispatchAttemptCommand,
    ) -> object:
        self.calls.append(command)
        return self.result


@dataclass(slots=True)
class FakeCommandLog:
    pending_commands: list[WorkflowCommand] = field(default_factory=list)
    completed: list[WorkflowCommandId] = field(default_factory=list)

    async def append_pending_command(self, command: WorkflowCommand) -> WorkflowCommand:
        self.pending_commands.append(command)
        return command

    async def mark_command_completed(
        self,
        *,
        command_id: WorkflowCommandId,
        completed_at: datetime,
    ) -> WorkflowCommand:
        del completed_at
        self.completed.append(command_id)
        return _command()

    async def list_pending_commands(
        self,
        *,
        workflow_run_id: str,
        limit: int,
    ) -> tuple[WorkflowCommand, ...]:
        del workflow_run_id, limit
        return ()


@dataclass(slots=True)
class FakeOutbox:
    events: list[WorkflowEvent] = field(default_factory=list)
    _next_sequence_number: int = 1

    async def append_event(self, event: WorkflowEvent) -> WorkflowEvent:
        persisted_event = WorkflowEvent(
            event_id=event.event_id,
            event_type=event.event_type,
            workflow_run_id=event.workflow_run_id,
            payload=event.payload,
            occurred_at=event.occurred_at,
            sequence_number=self._next_sequence_number,
            causation_command_id=event.causation_command_id,
            correlation_id=event.correlation_id,
        )
        self.events.append(persisted_event)
        self._next_sequence_number += 1
        return persisted_event

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
class FakeEventCursors:
    async def get_cursor(
        self,
        consumer_ref: WorkflowConsumerRef,
    ) -> WorkflowEventCursor | None:
        del consumer_ref
        return None

    async def save_cursor(self, cursor: WorkflowEventCursor) -> WorkflowEventCursor:
        return cursor


@dataclass(slots=True)
class FakeProgressSnapshots:
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
class FakeTimeline:
    entries: list[WorkflowTimelineEntry] = field(default_factory=list)

    async def append_entry(self, entry: WorkflowTimelineEntry) -> WorkflowTimelineEntry:
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
class FakeResourceUsage:
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
class FakeWorkflowUnitOfWork:
    command_log: FakeCommandLog = field(default_factory=FakeCommandLog)
    outbox: FakeOutbox = field(default_factory=FakeOutbox)
    event_cursors: FakeEventCursors = field(default_factory=FakeEventCursors)
    progress_snapshots: FakeProgressSnapshots = field(
        default_factory=FakeProgressSnapshots
    )
    timeline: FakeTimeline = field(default_factory=FakeTimeline)
    resource_usage: FakeResourceUsage = field(default_factory=FakeResourceUsage)

    async def commit(self) -> None:
        raise AssertionError("handler must not commit")

    async def rollback(self) -> None:
        raise AssertionError("handler must not rollback")


@dataclass(slots=True)
class InMemoryFrontendWorkflowEventRepository:
    events: dict[str, FrontendWorkflowEvent] = field(default_factory=dict)

    async def append(self, event: FrontendWorkflowEvent) -> FrontendWorkflowEvent:
        existing = self.events.get(event.projection_event_id)
        if existing is not None:
            return existing
        self.events[event.projection_event_id] = event
        return event


def _dispatch_payload() -> dict[str, object]:
    return {
        "work_item_id": "work-item-1",
        "attempt_id": "attempt-1",
        "schedule_payload": {
            "workflow_run_id": _workflow_run_id(),
            "group_ref": "group-1",
            "batch_ref": "batch-1",
            "source_claim_refs": ["claim-a", "claim-b"],
        },
        "llm_allocation": {
            "provider": "groq",
            "account_ref": "groq_org_primary",
            "model_ref": "openai/gpt-oss-120b",
        },
        "llm_execution_settings": {},
    }


def _dispatch() -> WorkItemAttemptDispatchForExecution:
    return WorkItemAttemptDispatchForExecution(
        attempt_id="attempt-1",
        work_item_id="work-item-1",
        attempt_number=1,
        lease_token=LeaseToken("lease-token-1"),
        worker_ref="knowledge-workbench-draft-claim-compaction-dispatch",
        dispatch_payload=_dispatch_payload(),
        started_at=_now(),
    )


def _execution_result(
    *,
    status: LlmDispatchExecutionStatus,
    output_payload: Mapping[str, object] | None,
    validation_metadata: Mapping[str, object] | None,
) -> ExecutePreparedLlmDispatchAttemptResult:
    return ExecutePreparedLlmDispatchAttemptResult(
        dispatch=_dispatch(),
        llm_result=LlmDispatchExecutionResult(
            status=status,
            finished_at=_now(),
            output_payload=output_payload,
            error_kind=None
            if status is LlmDispatchExecutionStatus.SUCCEEDED
            else "provider_error",
            next_attempt_at=_now() + timedelta(seconds=60)
            if status is LlmDispatchExecutionStatus.DEFERRED
            else None,
            capacity_observation={
                "provider": "groq",
                "account_ref": "groq_org_primary",
                "model_ref": "openai/gpt-oss-120b",
                "outcome_class": status.value,
                "observed_at": _now(),
                "actual_prompt_tokens": 10,
                "actual_completion_tokens": 5,
                "actual_total_tokens": 15,
            },
        ),
        outcome_result=RecordWorkItemAttemptOutcomeResult(work_item=None),
        validation_metadata=validation_metadata,
    )


def _valid_compacted_raw_text() -> str:
    return (
        '{"compacted_claims":[{'
        '"key":"k","claim":"Merged claim","claim_kind":"property",'
        '"source_claim_refs":["claim-a","claim-b"],'
        '"triples":[],"merge_decision":"merged"}]}'
    )


def _valid_reduced_raw_text() -> str:
    return '{"key":"k","claim":"Reduced claim","triples":[]}'


def test_validator_compacted_claims_success() -> None:
    validator = DraftClaimCompactionLlmDispatchOutputValidator(
        expected_output_kind=DraftClaimCompactionExpectedOutputKind.COMPACTED_CLAIMS,
        output_validator=DraftClaimCompactionOutputValidator(),
        source_claim_refs=("claim-a", "claim-b"),
    )

    result = validator.validate(
        dispatch_payload=_dispatch_payload(),
        output_payload={"raw_text": _valid_compacted_raw_text()},
        llm_status=LlmDispatchExecutionStatus.SUCCEEDED,
        finished_at=_now(),
        attempt_number=1,
    )

    assert result.status is LlmDispatchExecutionStatus.SUCCEEDED
    assert result.metadata["expected_output_kind"] == "compacted_claims"
    assert result.metadata["validated_compacted_claim_count"] == 1


def test_validator_reduced_rewrite_success() -> None:
    validator = DraftClaimCompactionLlmDispatchOutputValidator(
        expected_output_kind=DraftClaimCompactionExpectedOutputKind.REDUCED_REWRITE,
        output_validator=DraftClaimCompactionOutputValidator(),
    )

    result = validator.validate(
        dispatch_payload=_dispatch_payload(),
        output_payload={"raw_text": _valid_reduced_raw_text()},
        llm_status=LlmDispatchExecutionStatus.SUCCEEDED,
        finished_at=_now(),
        attempt_number=1,
    )

    assert result.status is LlmDispatchExecutionStatus.SUCCEEDED
    assert result.metadata["expected_output_kind"] == "reduced_rewrite"


def test_validator_invalid_json_is_retryable() -> None:
    validator = DraftClaimCompactionLlmDispatchOutputValidator(
        expected_output_kind=DraftClaimCompactionExpectedOutputKind.COMPACTED_CLAIMS,
        output_validator=DraftClaimCompactionOutputValidator(),
        source_claim_refs=("claim-a", "claim-b"),
    )

    result = validator.validate(
        dispatch_payload=_dispatch_payload(),
        output_payload={"raw_text": "{not-json"},
        llm_status=LlmDispatchExecutionStatus.SUCCEEDED,
        finished_at=_now(),
        attempt_number=1,
    )

    assert result.status is LlmDispatchExecutionStatus.RETRYABLE_FAILED
    assert result.error_kind == "draft_claim_compaction_output_validation_failed"


@pytest.mark.asyncio
async def test_handler_success_creates_apply_command_and_records_capacity() -> None:
    validator = DraftClaimCompactionLlmDispatchOutputValidator(
        expected_output_kind=DraftClaimCompactionExpectedOutputKind.COMPACTED_CLAIMS,
        output_validator=DraftClaimCompactionOutputValidator(),
        source_claim_refs=("claim-a", "claim-b"),
    )
    validation = validator.validate(
        dispatch_payload=_dispatch_payload(),
        output_payload={"raw_text": _valid_compacted_raw_text()},
        llm_status=LlmDispatchExecutionStatus.SUCCEEDED,
        finished_at=_now(),
        attempt_number=1,
    )
    workflow_uow = FakeWorkflowUnitOfWork()
    capacity_repository = FakeCapacityObservationRepository()

    result = await HandleExecuteDraftClaimCompactionCommandHandler().execute(
        HandleExecuteDraftClaimCompactionCommand(workflow_command=_command()),
        execute_prepared_llm_dispatch_attempt=FakeExecutePreparedDispatchAttempt(
            _execution_result(
                status=LlmDispatchExecutionStatus.SUCCEEDED,
                output_payload={"raw_text": _valid_compacted_raw_text()},
                validation_metadata=validation.metadata,
            )
        ),
        capacity_observation_repository=capacity_repository,
        draft_claim_compaction_output_validator=DraftClaimCompactionOutputValidator(),
        workflow_unit_of_work=workflow_uow,
    )

    assert result.outcome_status == "succeeded"
    assert [event.event_type for event in workflow_uow.outbox.events] == [
        KnowledgeExtractionCanonicalEventType.LLM_PROVIDER_CAPACITY_OBSERVED.value,
        KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_ATTEMPT_COMPLETED.value,
    ]
    capacity_event = workflow_uow.outbox.events[0]
    assert capacity_event.payload["operation_key"] == "execute_draft_claim_compaction"
    assert capacity_event.payload["canonical_phase"] == (
        KnowledgeExtractionCanonicalPhase.DRAFT_CLAIM_CLUSTERING.value
    )
    assert len(capacity_repository.observations) == 1
    assert len(workflow_uow.command_log.pending_commands) == 1
    assert workflow_uow.command_log.pending_commands[0].command_type == (
        KnowledgeExtractionCanonicalCommandType.APPLY_DRAFT_CLAIM_COMPACTION_RESULT.value
    )
    assert workflow_uow.command_log.pending_commands[0].payload[
        "compared_node_refs"
    ] == [
        "raw:workflow-1:group-1:claim-a",
        "raw:workflow-1:group-1:claim-b",
    ]
    assert workflow_uow.progress_snapshots.snapshot is not None
    assert len(workflow_uow.timeline.entries) == 1
    assert workflow_uow.command_log.completed == [_command().command_id]


@pytest.mark.asyncio
async def test_projects_llm_provider_capacity_observed_event_once() -> None:
    validator = DraftClaimCompactionLlmDispatchOutputValidator(
        expected_output_kind=DraftClaimCompactionExpectedOutputKind.COMPACTED_CLAIMS,
        output_validator=DraftClaimCompactionOutputValidator(),
        source_claim_refs=("claim-a", "claim-b"),
    )
    validation = validator.validate(
        dispatch_payload=_dispatch_payload(),
        output_payload={"raw_text": _valid_compacted_raw_text()},
        llm_status=LlmDispatchExecutionStatus.SUCCEEDED,
        finished_at=_now(),
        attempt_number=1,
    )
    repository = InMemoryFrontendWorkflowEventRepository()
    projection_writer = ProjectFrontendWorkflowEvent(
        projector=LlmProviderCapacityObservedFrontendWorkflowEventProjector(),
        repository=repository,
    )
    workflow_uow = FakeWorkflowUnitOfWork()

    await HandleExecuteDraftClaimCompactionCommandHandler().execute(
        HandleExecuteDraftClaimCompactionCommand(workflow_command=_command()),
        execute_prepared_llm_dispatch_attempt=FakeExecutePreparedDispatchAttempt(
            _execution_result(
                status=LlmDispatchExecutionStatus.SUCCEEDED,
                output_payload={"raw_text": _valid_compacted_raw_text()},
                validation_metadata=validation.metadata,
            )
        ),
        capacity_observation_repository=FakeCapacityObservationRepository(),
        draft_claim_compaction_output_validator=DraftClaimCompactionOutputValidator(),
        workflow_unit_of_work=workflow_uow,
        frontend_event_projection_writer=projection_writer,
    )

    assert len(repository.events) == 1
    projected = next(iter(repository.events.values()))
    assert projected.projection_type == "workflow_capacity_window_observed"
    assert projected.operation_key == "execute_draft_claim_compaction"
    assert projected.payload["window_key"] == (
        "groq:groq_org_primary:openai/gpt-oss-120b"
    )


def test_compaction_execute_handler_projects_after_canonical_outbox_append() -> None:
    source = inspect.getsource(HandleExecuteDraftClaimCompactionCommandHandler.execute)

    append_index = source.index("outbox.append_event")
    projection_index = source.index("frontend_event_projection_writer.execute")
    assert append_index < projection_index


def test_compaction_execute_handler_does_not_touch_live_state_for_projection() -> None:
    source = inspect.getsource(HandleExecuteDraftClaimCompactionCommandHandler.execute)

    for forbidden_marker in (
        "live_state",
        "fetch_workbench",
        "drain",
        "workflow_runner",
        "frontend_workflow_events",
    ):
        assert forbidden_marker not in source


@pytest.mark.asyncio
async def test_handler_reduced_rewrite_preserves_source_node_refs() -> None:
    validator = DraftClaimCompactionLlmDispatchOutputValidator(
        expected_output_kind=DraftClaimCompactionExpectedOutputKind.REDUCED_REWRITE,
        output_validator=DraftClaimCompactionOutputValidator(),
    )
    validation = validator.validate(
        dispatch_payload=_dispatch_payload(),
        output_payload={"raw_text": _valid_reduced_raw_text()},
        llm_status=LlmDispatchExecutionStatus.SUCCEEDED,
        finished_at=_now(),
        attempt_number=1,
    )
    workflow_uow = FakeWorkflowUnitOfWork()

    await HandleExecuteDraftClaimCompactionCommandHandler().execute(
        HandleExecuteDraftClaimCompactionCommand(
            workflow_command=_command(
                expected_output_kind="reduced_rewrite",
                source_node_refs=("compacted:a", "compacted:b"),
            )
        ),
        execute_prepared_llm_dispatch_attempt=FakeExecutePreparedDispatchAttempt(
            _execution_result(
                status=LlmDispatchExecutionStatus.SUCCEEDED,
                output_payload={"raw_text": _valid_reduced_raw_text()},
                validation_metadata=validation.metadata,
            )
        ),
        capacity_observation_repository=FakeCapacityObservationRepository(),
        draft_claim_compaction_output_validator=DraftClaimCompactionOutputValidator(),
        workflow_unit_of_work=workflow_uow,
    )

    apply_payload = workflow_uow.command_log.pending_commands[0].payload
    assert apply_payload["output_kind"] == "reduced_rewrite"
    assert apply_payload["source_node_refs"] == ["compacted:a", "compacted:b"]
    assert apply_payload["reduced_rewrite"] == {
        "key": "k",
        "claim": "Reduced claim",
        "triples": [],
    }


@pytest.mark.asyncio
async def test_handler_failure_does_not_create_apply_command() -> None:
    workflow_uow = FakeWorkflowUnitOfWork()

    await HandleExecuteDraftClaimCompactionCommandHandler().execute(
        HandleExecuteDraftClaimCompactionCommand(workflow_command=_command()),
        execute_prepared_llm_dispatch_attempt=FakeExecutePreparedDispatchAttempt(
            _execution_result(
                status=LlmDispatchExecutionStatus.RETRYABLE_FAILED,
                output_payload=None,
                validation_metadata=None,
            )
        ),
        capacity_observation_repository=FakeCapacityObservationRepository(),
        draft_claim_compaction_output_validator=DraftClaimCompactionOutputValidator(),
        workflow_unit_of_work=workflow_uow,
    )

    assert workflow_uow.command_log.pending_commands[0].command_type == (
        KnowledgeExtractionCanonicalCommandType.RECONCILE_DRAFT_CLAIM_COMPACTION_PROGRESS.value
    )
    assert workflow_uow.outbox.events[-1].event_type == (
        KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_ATTEMPT_RETRYABLE_FAILED.value
    )
