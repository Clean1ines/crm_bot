from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest
from pathlib import Path

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
    ClaimBuilderLlmDispatchOutputValidator,
    HandleExecuteClaimBuilderSectionCommand,
    HandleExecuteClaimBuilderSectionCommandHandler,
    HandleExecuteClaimBuilderSectionResult,
)
from src.contexts.knowledge_workbench.extraction.application.policies.claim_builder_output_validation_policy import (
    ClaimBuilderOutputValidationDecision,
    ClaimBuilderOutputValidationFailureReason,
    ClaimBuilderOutputValidationPolicy,
)
from src.contexts.knowledge_workbench.extraction.application.policies.claim_builder_attempt_next_action_policy import (
    ClaimBuilderAttemptNextActionKind,
)
from src.contexts.knowledge_workbench.extraction.application.ports.validated_draft_claim_observation_persistence_port import (
    PersistValidatedDraftClaimObservationsResult,
    ValidatedDraftClaimObservationCandidate,
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


def _claim_builder_provenance(
    *,
    workflow_run_id: str = _workflow_run_id(),
    source_unit_ref: str = "section-1",
    work_item_id: str = _work_item_id(),
) -> dict[str, object]:
    return {
        "workflow_run_id": workflow_run_id,
        "stage_run_id": "claim_builder_section_extraction",
        "source_unit_ref": source_unit_ref,
        "work_item_id": work_item_id,
        "prompt_id": "faq_claim_observations",
        "prompt_version": "v1",
    }


def _provider_messages(*, source_unit_ref: str = "section-1") -> list[dict[str, str]]:
    return [
        {
            "role": "user",
            "content": (
                f"source_unit_ref: {source_unit_ref}\n"
                "heading_path: /\n\n"
                "Product System turns documents into knowledge. "
                "Цены не описаны."
            ),
        }
    ]


def _schedule_payload(
    *,
    claim_builder_provenance: dict[str, object] | None = None,
    source_unit_ref: str = "section-1",
) -> dict[str, object]:
    return {
        "workflow_run_id": _workflow_run_id(),
        "source_document_ref": "source-document:project-1:abc",
        "source_unit_ref": source_unit_ref,
        "source_unit_ordinal": 0,
        "phase": "claim_builder_section_extraction",
        "provider_messages": _provider_messages(source_unit_ref=source_unit_ref),
        "claim_builder_provenance": _claim_builder_provenance(
            source_unit_ref=source_unit_ref,
        )
        if claim_builder_provenance is None
        else claim_builder_provenance,
    }


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


def _dispatch(
    *,
    schedule_payload: dict[str, object] | None = None,
) -> WorkItemAttemptDispatchForExecution:
    return WorkItemAttemptDispatchForExecution(
        attempt_id=_attempt_id(),
        work_item_id=_work_item_id(),
        attempt_number=1,
        lease_token=LeaseToken("lease-token-1"),
        worker_ref="worker-1",
        dispatch_payload={
            "work_item_id": _work_item_id(),
            "schedule_payload": _schedule_payload()
            if schedule_payload is None
            else schedule_payload,
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
    *,
    dispatch: WorkItemAttemptDispatchForExecution | None = None,
) -> ExecutePreparedLlmDispatchAttemptResult:
    prepared_dispatch = _dispatch() if dispatch is None else dispatch
    if status is LlmDispatchExecutionStatus.SUCCEEDED:
        llm_result = LlmDispatchExecutionResult(
            status=status,
            finished_at=_finished_at(),
            output_payload={
                "raw_text": (
                    '{"claims":[{"claim":"Product System turns documents into '
                    'knowledge.","granularity":"atomic","possible_questions":'
                    '["Что делает Product System?"],"exclusion_scope":"Цены не '
                    'описаны.","evidence_block":"Product System turns documents '
                    'into knowledge."}]}'
                )
            },
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
        dispatch=prepared_dispatch,
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
        if (
            command.output_validator is None
            or self.result.validation_metadata is not None
            or self.result.llm_result.status is not LlmDispatchExecutionStatus.SUCCEEDED
        ):
            return self.result

        validation_result = command.output_validator.validate(
            dispatch_payload=self.result.dispatch.dispatch_payload,
            output_payload=self.result.llm_result.output_payload,
            llm_status=self.result.llm_result.status,
            finished_at=self.result.llm_result.finished_at,
            attempt_number=self.result.dispatch.attempt_number,
        )
        return ExecutePreparedLlmDispatchAttemptResult(
            dispatch=self.result.dispatch,
            llm_result=LlmDispatchExecutionResult(
                status=validation_result.status,
                finished_at=self.result.llm_result.finished_at,
                output_payload=self.result.llm_result.output_payload,
                error_kind=validation_result.error_kind,
                next_attempt_at=validation_result.next_attempt_at,
                capacity_observation=self.result.llm_result.capacity_observation,
            ),
            outcome_result=self.result.outcome_result,
            validation_metadata=dict(validation_result.metadata),
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
class FakeDraftClaimObservationPersistence:
    candidates: list[ValidatedDraftClaimObservationCandidate] = field(
        default_factory=list,
    )

    async def persist_validated_claims(
        self,
        candidates: tuple[ValidatedDraftClaimObservationCandidate, ...],
    ) -> PersistValidatedDraftClaimObservationsResult:
        self.candidates.extend(candidates)
        return PersistValidatedDraftClaimObservationsResult(
            persisted_count=len(candidates),
        )


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
    HandleExecuteClaimBuilderSectionResult,
    FakeExecutePreparedLlmDispatchAttempt,
    FakeCapacityObservationRepository,
    FakeWorkflowRuntimeUnitOfWork,
    FakeDraftClaimObservationPersistence,
]:
    executor = FakeExecutePreparedLlmDispatchAttempt(
        result=execution_result or _execution_result(),
    )
    capacity_repository = FakeCapacityObservationRepository()
    workflow_unit_of_work = FakeWorkflowRuntimeUnitOfWork()
    draft_persistence = FakeDraftClaimObservationPersistence()
    result = await HandleExecuteClaimBuilderSectionCommandHandler().execute(
        HandleExecuteClaimBuilderSectionCommand(
            workflow_command=workflow_command or _workflow_command(),
        ),
        execute_prepared_llm_dispatch_attempt=executor,
        capacity_observation_repository=capacity_repository,
        claim_builder_output_validation_policy=ClaimBuilderOutputValidationPolicy(),
        draft_claim_observation_persistence=draft_persistence,
        workflow_unit_of_work=workflow_unit_of_work,
    )
    return (
        result,
        executor,
        capacity_repository,
        workflow_unit_of_work,
        draft_persistence,
    )


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
    result, executor, _, _, _ = await _execute()

    assert result.dispatch_attempt_id == _attempt_id()
    assert result.work_item_id == _work_item_id()
    assert result.outcome_status == LlmDispatchExecutionStatus.SUCCEEDED.value
    assert len(executor.calls) == 1
    assert executor.calls[0].attempt_id == _attempt_id()
    assert executor.calls[0].output_validator is not None


@pytest.mark.asyncio
async def test_records_capacity_observation_feedback_contract() -> None:
    _, _, capacity_repository, _, _ = await _execute()

    assert len(capacity_repository.observations) == 1
    observation = capacity_repository.observations[0]
    assert observation.provider == "groq"
    assert observation.account_ref == "groq_org_primary"
    assert observation.model_ref == "qwen/qwen3-32b"
    assert observation.actual_total_tokens == 15


@pytest.mark.asyncio
async def test_appends_outcome_and_capacity_events() -> None:
    _, _, _, workflow_unit_of_work, _ = await _execute()

    assert tuple(event.event_type for event in workflow_unit_of_work.outbox.events) == (
        KnowledgeExtractionCanonicalEventType.LLM_PROVIDER_CAPACITY_OBSERVED.value,
        KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SECTION_EXTRACTED.value,
    )
    outcome_event = workflow_unit_of_work.outbox.events[1]
    assert outcome_event.payload["dispatch_attempt_id"] == _attempt_id()
    assert outcome_event.payload["work_item_id"] == _work_item_id()
    assert outcome_event.payload["outcome_status"] == "succeeded"
    assert outcome_event.payload["actual_total_tokens"] == 15
    assert outcome_event.payload["validation_decision"] == (
        ClaimBuilderOutputValidationDecision.VALID_CLAIMS.value
    )
    assert outcome_event.payload["validated_claim_count"] == 1
    assert outcome_event.payload["claim_builder_attempt_next_action_kind"] == (
        ClaimBuilderAttemptNextActionKind.PERSIST_VALID_CLAIMS.value
    )
    assert outcome_event.payload["claim_builder_attempt_next_action_reason"] == (
        "valid_claims"
    )
    assert outcome_event.payload["claim_builder_attempt_next_model_strategy"] is None
    assert outcome_event.payload["claim_builder_should_persist_claims"] is True
    assert (
        outcome_event.payload["claim_builder_should_mark_work_item_completed"] is True
    )
    assert outcome_event.payload["claim_builder_requires_source_split"] is False
    assert outcome_event.payload["claim_builder_next_run_after"] is None


@pytest.mark.asyncio
async def test_appends_reconcile_claim_builder_progress_command() -> None:
    _, _, _, workflow_unit_of_work, _ = await _execute()

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
    result, _, _, workflow_unit_of_work, _ = await _execute()

    assert result.completed_command_id == _workflow_command().command_id
    assert workflow_unit_of_work.command_log.completed_command_ids == [
        _workflow_command().command_id,
    ]


@pytest.mark.asyncio
async def test_updates_progress_snapshot_and_timeline() -> None:
    _, _, _, workflow_unit_of_work, _ = await _execute()

    snapshot = workflow_unit_of_work.progress_snapshots.snapshot
    assert snapshot is not None
    assert snapshot.current_phase == "CLAIM_BUILDER_SECTION_EXTRACTION"
    assert snapshot.completed_work_items == 1
    assert snapshot.domain_counters["executed_attempt_count"] == 1
    assert snapshot.domain_counters["capacity_observation_count"] == 1
    assert snapshot.domain_counters["claim_builder_valid_output_count"] == 1
    assert snapshot.domain_counters["claim_builder_valid_claim_count"] == 1
    assert snapshot.domain_counters["draft_claim_observation_count"] == 1

    assert tuple(entry.message for entry in workflow_unit_of_work.timeline.entries) == (
        "Claim builder section attempt executed",
    )
    assert workflow_unit_of_work.timeline.entries[0].attempt_id == _attempt_id()


@pytest.mark.asyncio
async def test_deferred_outcome_updates_deferred_progress() -> None:
    _, _, _, workflow_unit_of_work, draft_persistence = await _execute(
        execution_result=_execution_result(LlmDispatchExecutionStatus.DEFERRED),
    )

    snapshot = workflow_unit_of_work.progress_snapshots.snapshot
    assert snapshot is not None
    assert snapshot.deferred_work_items == 1
    assert workflow_unit_of_work.outbox.events[1].event_type == (
        KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SECTION_EXTRACTION_DEFERRED.value
    )


@pytest.mark.asyncio
async def test_llm_succeeded_invalid_claim_output_becomes_retryable_failed() -> None:
    invalid_result = ExecutePreparedLlmDispatchAttemptResult(
        dispatch=_dispatch(),
        llm_result=LlmDispatchExecutionResult(
            status=LlmDispatchExecutionStatus.RETRYABLE_FAILED,
            finished_at=_finished_at(),
            output_payload={"raw_text": '{"claims":[]}'},
            error_kind="claim_builder_output_validation_failed",
            next_attempt_at=_finished_at() + timedelta(seconds=1),
            capacity_observation={
                **_capacity_payload(),
                "outcome_class": LlmDispatchExecutionStatus.RETRYABLE_FAILED.value,
            },
        ),
        outcome_result=RecordWorkItemAttemptOutcomeResult(
            work_item=WorkItem(
                work_item_id=_work_item_id(),
                work_kind=WorkKind(
                    "knowledge_workbench.claim_builder.section_extraction"
                ),
                status=WorkItemStatus.RETRYABLE_FAILED,
            )
        ),
        validation_metadata={
            "validation_decision": (
                ClaimBuilderOutputValidationDecision.RETRY_FALLBACK_MODEL.value
            ),
            "validation_failure_reason": (
                ClaimBuilderOutputValidationFailureReason.CLAIMS_EMPTY_RETRY_REQUIRED.value
            ),
            "validated_claim_count": 0,
            "claim_builder_attempt_next_action_kind": (
                ClaimBuilderAttemptNextActionKind.RETRY_FALLBACK_MODEL.value
            ),
            "claim_builder_attempt_next_action_reason": (
                ClaimBuilderOutputValidationFailureReason.CLAIMS_EMPTY_RETRY_REQUIRED.value
            ),
            "claim_builder_attempt_next_model_strategy": "FALLBACK_MODEL_REQUIRED",
            "claim_builder_should_persist_claims": False,
            "claim_builder_should_mark_work_item_completed": False,
            "claim_builder_requires_source_split": False,
            "claim_builder_next_run_after": None,
            "retry_recommended": True,
        },
    )

    (
        result,
        _,
        capacity_repository,
        workflow_unit_of_work,
        draft_persistence,
    ) = await _execute(
        execution_result=invalid_result,
    )

    assert result.outcome_status == LlmDispatchExecutionStatus.RETRYABLE_FAILED.value
    assert len(capacity_repository.observations) == 1
    assert workflow_unit_of_work.outbox.events[1].event_type == (
        KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SECTION_EXTRACTION_RETRYABLE_FAILED.value
    )
    assert workflow_unit_of_work.outbox.events[1].payload["validation_decision"] == (
        ClaimBuilderOutputValidationDecision.RETRY_FALLBACK_MODEL.value
    )
    assert workflow_unit_of_work.outbox.events[1].payload["retry_recommended"] is True
    assert (
        workflow_unit_of_work.outbox.events[1].payload[
            "claim_builder_attempt_next_action_kind"
        ]
        == ClaimBuilderAttemptNextActionKind.RETRY_FALLBACK_MODEL.value
    )
    assert (
        workflow_unit_of_work.outbox.events[1].payload[
            "claim_builder_attempt_next_model_strategy"
        ]
        == "FALLBACK_MODEL_REQUIRED"
    )
    assert (
        workflow_unit_of_work.outbox.events[1].payload[
            "claim_builder_should_persist_claims"
        ]
        is False
    )
    assert (
        workflow_unit_of_work.outbox.events[1].payload[
            "claim_builder_should_mark_work_item_completed"
        ]
        is False
    )
    assert tuple(
        command.command_type
        for command in workflow_unit_of_work.command_log.pending_commands
    ) == (
        KnowledgeExtractionCanonicalCommandType.RECONCILE_CLAIM_BUILDER_PROGRESS.value,
    )

    snapshot = workflow_unit_of_work.progress_snapshots.snapshot
    assert snapshot is not None
    assert snapshot.retryable_failed_work_items == 1
    assert snapshot.domain_counters["claim_builder_invalid_output_count"] == 1
    assert (
        snapshot.domain_counters["claim_builder_validation_retryable_failed_count"] == 1
    )
    assert snapshot.domain_counters["claim_builder_retry_action_count"] == 1
    assert snapshot.domain_counters["claim_builder_fallback_retry_required_count"] == 1


@pytest.mark.asyncio
async def test_valid_empty_output_after_retry_is_accepted_as_extracted() -> None:
    valid_empty_result = ExecutePreparedLlmDispatchAttemptResult(
        dispatch=_dispatch(),
        llm_result=LlmDispatchExecutionResult(
            status=LlmDispatchExecutionStatus.SUCCEEDED,
            finished_at=_finished_at(),
            output_payload={"raw_text": '{"claims":[]}'},
            capacity_observation=_capacity_payload(),
        ),
        outcome_result=RecordWorkItemAttemptOutcomeResult(
            work_item=WorkItem(
                work_item_id=_work_item_id(),
                work_kind=WorkKind(
                    "knowledge_workbench.claim_builder.section_extraction"
                ),
                status=WorkItemStatus.COMPLETED,
            )
        ),
        validation_metadata={
            "validation_decision": (
                ClaimBuilderOutputValidationDecision.VALID_EMPTY.value
            ),
            "validation_failure_reason": None,
            "validated_claim_count": 0,
            "claim_builder_attempt_next_action_kind": (
                ClaimBuilderAttemptNextActionKind.ACCEPT_VALID_EMPTY.value
            ),
            "claim_builder_attempt_next_action_reason": "valid_empty",
            "claim_builder_attempt_next_model_strategy": None,
            "claim_builder_should_persist_claims": False,
            "claim_builder_should_mark_work_item_completed": True,
            "claim_builder_requires_source_split": False,
            "claim_builder_next_run_after": None,
            "retry_recommended": False,
        },
    )

    _, _, _, workflow_unit_of_work, draft_persistence = await _execute(
        execution_result=valid_empty_result,
    )

    assert workflow_unit_of_work.outbox.events[1].event_type == (
        KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SECTION_EXTRACTED.value
    )
    assert workflow_unit_of_work.outbox.events[1].payload["validation_decision"] == (
        ClaimBuilderOutputValidationDecision.VALID_EMPTY.value
    )
    assert workflow_unit_of_work.outbox.events[1].payload["validated_claim_count"] == 0
    assert (
        workflow_unit_of_work.outbox.events[1].payload[
            "claim_builder_attempt_next_action_kind"
        ]
        == ClaimBuilderAttemptNextActionKind.ACCEPT_VALID_EMPTY.value
    )
    assert (
        workflow_unit_of_work.outbox.events[1].payload[
            "claim_builder_should_persist_claims"
        ]
        is False
    )
    assert (
        workflow_unit_of_work.outbox.events[1].payload[
            "claim_builder_should_mark_work_item_completed"
        ]
        is True
    )
    assert draft_persistence.candidates == []


def test_source_unit_text_missing_fails_explicitly() -> None:
    validator = ClaimBuilderLlmDispatchOutputValidator(
        policy=ClaimBuilderOutputValidationPolicy(),
    )

    with pytest.raises(ValueError, match="source_unit_text"):
        validator.validate(
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
            output_payload={
                "raw_text": (
                    '{"claims":[{"claim":"Product System turns documents into '
                    'knowledge.","granularity":"atomic","possible_questions":'
                    '["Что делает Product System?"],"exclusion_scope":"Цены не '
                    'описаны.","evidence_block":"Product System turns documents '
                    'into knowledge."}]}'
                )
            },
            llm_status=LlmDispatchExecutionStatus.SUCCEEDED,
            finished_at=_finished_at(),
            attempt_number=1,
        )


@pytest.mark.asyncio
async def test_valid_claims_are_persisted_as_draft_claim_observations() -> None:
    _, _, _, workflow_unit_of_work, draft_persistence = await _execute()

    assert len(draft_persistence.candidates) == 1
    candidate = draft_persistence.candidates[0]
    assert candidate.workflow_run_id == _workflow_run_id()
    assert candidate.stage_run_id == "claim_builder_section_extraction"
    assert candidate.prompt_id == "faq_claim_observations"
    assert candidate.prompt_version == "v1"
    assert candidate.source_document_ref == "source-document:project-1:abc"
    assert candidate.source_unit_ref == "section-1"
    assert candidate.work_item_id == _work_item_id()
    assert candidate.dispatch_attempt_id == _attempt_id()
    assert candidate.provider == "groq"
    assert candidate.model_ref == "qwen/qwen3-32b"
    assert candidate.claim_index == 0
    assert candidate.claim == "Product System turns documents into knowledge."
    assert candidate.validation_decision == (
        ClaimBuilderOutputValidationDecision.VALID_CLAIMS.value
    )

    snapshot = workflow_unit_of_work.progress_snapshots.snapshot
    assert snapshot is not None
    assert snapshot.domain_counters["claim_builder_persisted_draft_claim_count"] == 1
    assert snapshot.domain_counters["draft_claim_observation_count"] == 1


@pytest.mark.asyncio
async def test_valid_claim_persistence_requires_claim_builder_provenance() -> None:
    schedule_payload = _schedule_payload()
    del schedule_payload["claim_builder_provenance"]

    with pytest.raises(ValueError, match="claim_builder_provenance"):
        await _execute(
            execution_result=_execution_result(
                dispatch=_dispatch(schedule_payload=schedule_payload),
            ),
        )


@pytest.mark.asyncio
async def test_valid_claim_persistence_rejects_mismatched_provenance_workflow_run_id() -> (
    None
):
    schedule_payload = _schedule_payload(
        claim_builder_provenance={
            **_claim_builder_provenance(),
            "workflow_run_id": "knowledge-extraction:other",
        },
    )

    with pytest.raises(ValueError, match="workflow_run_id"):
        await _execute(
            execution_result=_execution_result(
                dispatch=_dispatch(schedule_payload=schedule_payload),
            ),
        )


@pytest.mark.asyncio
async def test_valid_claim_persistence_rejects_mismatched_provenance_source_unit_ref() -> (
    None
):
    schedule_payload = _schedule_payload(
        claim_builder_provenance={
            **_claim_builder_provenance(),
            "source_unit_ref": "section-other",
        },
    )

    with pytest.raises(ValueError, match="source_unit_ref"):
        await _execute(
            execution_result=_execution_result(
                dispatch=_dispatch(schedule_payload=schedule_payload),
            ),
        )


@pytest.mark.asyncio
async def test_valid_claim_persistence_rejects_mismatched_provenance_work_item_id() -> (
    None
):
    schedule_payload = _schedule_payload(
        claim_builder_provenance={
            **_claim_builder_provenance(),
            "work_item_id": "work-other",
        },
    )

    with pytest.raises(ValueError, match="work_item_id"):
        await _execute(
            execution_result=_execution_result(
                dispatch=_dispatch(schedule_payload=schedule_payload),
            ),
        )


@pytest.mark.asyncio
async def test_invalid_retry_decision_persists_zero_draft_claims() -> None:
    invalid_result = ExecutePreparedLlmDispatchAttemptResult(
        dispatch=_dispatch(),
        llm_result=LlmDispatchExecutionResult(
            status=LlmDispatchExecutionStatus.RETRYABLE_FAILED,
            finished_at=_finished_at(),
            output_payload={"raw_text": '{"claims":[]}'},
            error_kind="claim_builder_output_validation_failed",
            next_attempt_at=_finished_at() + timedelta(seconds=1),
            capacity_observation={
                **_capacity_payload(),
                "outcome_class": LlmDispatchExecutionStatus.RETRYABLE_FAILED.value,
            },
        ),
        outcome_result=RecordWorkItemAttemptOutcomeResult(
            work_item=WorkItem(
                work_item_id=_work_item_id(),
                work_kind=WorkKind(
                    "knowledge_workbench.claim_builder.section_extraction"
                ),
                status=WorkItemStatus.RETRYABLE_FAILED,
            )
        ),
        validation_metadata={
            "claim_builder_attempt_outcome_kind": "RETRY_FALLBACK_MODEL",
            "validation_decision": (
                ClaimBuilderOutputValidationDecision.RETRY_FALLBACK_MODEL.value
            ),
            "validation_failure_reason": (
                ClaimBuilderOutputValidationFailureReason.CLAIMS_EMPTY_RETRY_REQUIRED.value
            ),
            "validated_claim_count": 0,
            "next_model_strategy": "FALLBACK_MODEL_REQUIRED",
            "claim_builder_attempt_next_action_kind": (
                ClaimBuilderAttemptNextActionKind.RETRY_FALLBACK_MODEL.value
            ),
            "claim_builder_attempt_next_action_reason": (
                ClaimBuilderOutputValidationFailureReason.CLAIMS_EMPTY_RETRY_REQUIRED.value
            ),
            "claim_builder_attempt_next_model_strategy": "FALLBACK_MODEL_REQUIRED",
            "claim_builder_should_persist_claims": False,
            "claim_builder_should_mark_work_item_completed": False,
            "claim_builder_requires_source_split": False,
            "claim_builder_next_run_after": None,
            "retry_recommended": True,
            "_validated_claims": (),
        },
    )

    _, _, _, workflow_unit_of_work, draft_persistence = await _execute(
        execution_result=invalid_result,
    )

    assert draft_persistence.candidates == []
    assert tuple(event.event_type for event in workflow_unit_of_work.outbox.events) == (
        KnowledgeExtractionCanonicalEventType.LLM_PROVIDER_CAPACITY_OBSERVED.value,
        KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SECTION_EXTRACTION_RETRYABLE_FAILED.value,
    )
    assert workflow_unit_of_work.outbox.events[1].payload["next_model_strategy"] == (
        "FALLBACK_MODEL_REQUIRED"
    )
    assert (
        workflow_unit_of_work.outbox.events[1].payload[
            "claim_builder_attempt_next_action_kind"
        ]
        == ClaimBuilderAttemptNextActionKind.RETRY_FALLBACK_MODEL.value
    )
    assert (
        workflow_unit_of_work.outbox.events[1].payload[
            "claim_builder_should_persist_claims"
        ]
        is False
    )


def test_truncated_output_metadata_uses_larger_output_next_action() -> None:
    validator = ClaimBuilderLlmDispatchOutputValidator(
        policy=ClaimBuilderOutputValidationPolicy(),
    )

    result = validator.validate(
        dispatch_payload=_dispatch().dispatch_payload,
        output_payload={
            "raw_text": '{"claims":[]}',
            "output_truncated": True,
        },
        llm_status=LlmDispatchExecutionStatus.SUCCEEDED,
        finished_at=_finished_at(),
        attempt_number=1,
    )

    assert result.status is LlmDispatchExecutionStatus.RETRYABLE_FAILED
    assert result.metadata["claim_builder_attempt_next_action_kind"] == (
        ClaimBuilderAttemptNextActionKind.RETRY_LARGER_OUTPUT_LIMIT_MODEL.value
    )
    assert result.metadata["claim_builder_attempt_next_model_strategy"] == (
        "LARGER_OUTPUT_LIMIT_MODEL_REQUIRED"
    )
    assert result.metadata["claim_builder_should_persist_claims"] is False


def test_retry_same_model_metadata_uses_retry_same_model_next_action() -> None:
    validator = ClaimBuilderLlmDispatchOutputValidator(
        policy=ClaimBuilderOutputValidationPolicy(),
    )

    result = validator.validate(
        dispatch_payload=_dispatch().dispatch_payload,
        output_payload={"raw_text": '{"claims":"not-list"}'},
        llm_status=LlmDispatchExecutionStatus.SUCCEEDED,
        finished_at=_finished_at(),
        attempt_number=1,
    )

    assert result.status is LlmDispatchExecutionStatus.RETRYABLE_FAILED
    assert result.metadata["claim_builder_attempt_next_action_kind"] == (
        ClaimBuilderAttemptNextActionKind.RETRY_SAME_MODEL.value
    )
    assert result.metadata["claim_builder_attempt_next_model_strategy"] == "SAME_MODEL"
    assert result.metadata["claim_builder_should_persist_claims"] is False


@pytest.mark.asyncio
async def test_terminal_invalid_metadata_emits_terminal_failure_action() -> None:
    terminal_result = ExecutePreparedLlmDispatchAttemptResult(
        dispatch=_dispatch(),
        llm_result=LlmDispatchExecutionResult(
            status=LlmDispatchExecutionStatus.TERMINAL_FAILED,
            finished_at=_finished_at(),
            output_payload={"raw_text": '{"claims":[]}'},
            error_kind="claim_builder_output_validation_failed",
            capacity_observation={
                **_capacity_payload(),
                "outcome_class": LlmDispatchExecutionStatus.TERMINAL_FAILED.value,
            },
        ),
        outcome_result=RecordWorkItemAttemptOutcomeResult(
            work_item=WorkItem(
                work_item_id=_work_item_id(),
                work_kind=WorkKind(
                    "knowledge_workbench.claim_builder.section_extraction"
                ),
                status=WorkItemStatus.TERMINAL_FAILED,
            )
        ),
        validation_metadata={
            "claim_builder_attempt_outcome_kind": "TERMINAL_INVALID",
            "validation_decision": "TERMINAL_INVALID",
            "validation_failure_reason": (
                ClaimBuilderOutputValidationFailureReason.CLAIM_FIELD_SET_INVALID.value
            ),
            "validated_claim_count": 0,
            "next_model_strategy": None,
            "claim_builder_attempt_next_action_kind": (
                ClaimBuilderAttemptNextActionKind.TERMINAL_FAILURE.value
            ),
            "claim_builder_attempt_next_action_reason": (
                ClaimBuilderOutputValidationFailureReason.CLAIM_FIELD_SET_INVALID.value
            ),
            "claim_builder_attempt_next_model_strategy": None,
            "claim_builder_should_persist_claims": False,
            "claim_builder_should_mark_work_item_completed": False,
            "claim_builder_requires_source_split": False,
            "claim_builder_next_run_after": None,
            "retry_recommended": False,
            "_validated_claims": (),
        },
    )

    _, _, _, workflow_unit_of_work, draft_persistence = await _execute(
        execution_result=terminal_result,
    )

    assert draft_persistence.candidates == []
    assert workflow_unit_of_work.outbox.events[1].event_type == (
        KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SECTION_EXTRACTION_TERMINAL_FAILED.value
    )
    assert (
        workflow_unit_of_work.outbox.events[1].payload[
            "claim_builder_attempt_next_action_kind"
        ]
        == ClaimBuilderAttemptNextActionKind.TERMINAL_FAILURE.value
    )

    snapshot = workflow_unit_of_work.progress_snapshots.snapshot
    assert snapshot is not None
    assert snapshot.domain_counters["claim_builder_terminal_invalid_count"] == 1


def test_execute_retry_after_recorded_outcome_is_guarded_before_llm_call() -> None:
    source = Path(
        "src/interfaces/composition/execute_prepared_llm_dispatch_attempt.py",
    ).read_text(encoding="utf-8")

    recorded_lookup_index = source.index("get_recorded_attempt_outcome")
    llm_call_index = source.index("execute_dispatch(")

    assert recorded_lookup_index < llm_call_index
    assert "recorded_outcome_reader=outcome_repository" in Path(
        "src/interfaces/composition/knowledge_extraction_after_upload_composition.py",
    ).read_text(encoding="utf-8")
