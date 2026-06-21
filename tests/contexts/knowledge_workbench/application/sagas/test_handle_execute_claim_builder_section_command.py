from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import cast
import inspect

import pytest
from pathlib import Path

from src.contexts.capacity_runtime.application.ports.llm_attempt_capacity_observation_repository_port import (
    LlmAttemptCapacityObservation,
    LlmAttemptCapacityObservationRepositoryPort,
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
    _event_type_for_status,
    _source_context_text,
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
    KnowledgeExtractionCanonicalPhase,
)
from src.contexts.knowledge_workbench.observability.application.models.frontend_workflow_event import (
    FrontendWorkflowEvent,
)
from src.contexts.knowledge_workbench.observability.application.projectors.claim_builder_frontend_workflow_event_projector import (
    ClaimBuilderFrontendWorkflowEventProjector,
)
from src.contexts.knowledge_workbench.observability.application.projectors.llm_provider_capacity_observed_frontend_workflow_event_projector import (
    LlmProviderCapacityObservedFrontendWorkflowEventProjector,
)
from src.contexts.knowledge_workbench.observability.application.projectors.project_frontend_workflow_event import (
    ProjectFrontendWorkflowEvent,
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
from src.contexts.workflow_runtime.application.ports.workflow_runtime_unit_of_work_port import (
    WorkflowRuntimeUnitOfWorkPort,
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
                    'описаны."}]}'
                )
            },
            capacity_observation=_capacity_payload(),
        )
        work_status = WorkItemStatus.COMPLETED
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

    async def observations_for_accounts_since(
        self,
        *,
        provider: str,
        account_refs: tuple[str, ...],
        model_ref: str,
        since: datetime,
    ) -> tuple[LlmAttemptCapacityObservation, ...]:
        del since
        return tuple(
            observation
            for observation in self.observations
            if observation.provider == provider
            and observation.account_ref in account_refs
            and observation.model_ref == model_ref
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


@dataclass(slots=True)
class InMemoryFrontendWorkflowEventRepository:
    events: dict[str, FrontendWorkflowEvent] = field(default_factory=dict)

    async def append(self, event: FrontendWorkflowEvent) -> FrontendWorkflowEvent:
        existing = self.events.get(event.projection_event_id)
        if existing is not None:
            return existing
        self.events[event.projection_event_id] = event
        return event


async def _execute(
    *,
    workflow_command: WorkflowCommand | None = None,
    execution_result: ExecutePreparedLlmDispatchAttemptResult | None = None,
    frontend_event_projection_writer: ProjectFrontendWorkflowEvent | None = None,
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
        capacity_observation_repository=cast(
            LlmAttemptCapacityObservationRepositoryPort,
            capacity_repository,
        ),
        claim_builder_output_validation_policy=ClaimBuilderOutputValidationPolicy(),
        draft_claim_observation_persistence=draft_persistence,
        workflow_unit_of_work=cast(
            WorkflowRuntimeUnitOfWorkPort,
            workflow_unit_of_work,
        ),
        frontend_event_projection_writer=frontend_event_projection_writer,
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
    capacity_event = workflow_unit_of_work.outbox.events[0]
    assert capacity_event.payload["operation_key"] == "execute_claim_builder_section"
    assert capacity_event.payload["canonical_phase"] == (
        KnowledgeExtractionCanonicalPhase.CLAIM_BUILDER_SECTION_EXTRACTION.value
    )
    outcome_event = workflow_unit_of_work.outbox.events[1]
    assert outcome_event.payload["operation_key"] == "execute_claim_builder_section"
    assert outcome_event.payload["canonical_phase"] == (
        KnowledgeExtractionCanonicalPhase.CLAIM_BUILDER_SECTION_EXTRACTION.value
    )
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
async def test_projects_llm_provider_capacity_observed_event_once() -> None:
    repository = InMemoryFrontendWorkflowEventRepository()
    projection_writer = ProjectFrontendWorkflowEvent(
        projector=LlmProviderCapacityObservedFrontendWorkflowEventProjector(),
        repository=repository,
    )

    _, _, _, workflow_unit_of_work, _ = await _execute(
        frontend_event_projection_writer=projection_writer,
    )

    capacity_event = workflow_unit_of_work.outbox.events[0]
    assert (
        capacity_event.event_type
        == KnowledgeExtractionCanonicalEventType.LLM_PROVIDER_CAPACITY_OBSERVED.value
    )
    assert len(repository.events) == 1
    projected = next(iter(repository.events.values()))
    assert projected.projection_type == "workflow_capacity_window_observed"
    assert projected.payload["window_key"] == "groq:groq_org_primary:qwen/qwen3-32b"
    assert projected.payload["account_ref"] == "groq_org_primary"


@pytest.mark.asyncio
async def test_projects_claim_builder_section_extracted_event_once() -> None:
    repository = InMemoryFrontendWorkflowEventRepository()
    projection_writer = ProjectFrontendWorkflowEvent(
        projector=ClaimBuilderFrontendWorkflowEventProjector(),
        repository=repository,
    )

    await _execute(frontend_event_projection_writer=projection_writer)

    extracted = [
        event
        for event in repository.events.values()
        if event.projection_type == "workflow_claim_builder_section_extracted"
    ]
    assert len(extracted) == 1
    assert extracted[0].operation_key == "execute_claim_builder_section"
    assert extracted[0].payload["source_document_ref"] == (
        "source-document:project-1:abc"
    )
    assert extracted[0].payload["source_unit_ref"] == "section-1"
    assert extracted[0].payload["draft_claims_available"] is True
    assert extracted[0].payload["draft_claims_scope"]["work_item_id"] == (
        _work_item_id()
    )


@pytest.mark.asyncio
async def test_projects_claim_builder_section_retryable_failed_event_once() -> None:
    repository = InMemoryFrontendWorkflowEventRepository()
    projection_writer = ProjectFrontendWorkflowEvent(
        projector=ClaimBuilderFrontendWorkflowEventProjector(),
        repository=repository,
    )

    await _execute(
        execution_result=_execution_result(LlmDispatchExecutionStatus.RETRYABLE_FAILED),
        frontend_event_projection_writer=projection_writer,
    )

    retryable = [
        event
        for event in repository.events.values()
        if event.projection_type == "workflow_claim_builder_section_retryable_failed"
    ]
    assert len(retryable) == 1
    assert "next_attempt_at" not in retryable[0].payload
    assert "claim_builder_next_run_after" not in retryable[0].payload
    assert retryable[0].payload["source_unit_ref"] == "section-1"
    assert retryable[0].payload["retry_eligibility"] == "eligible_for_future_admission"
    assert retryable[0].payload["retry_driver"] == "capacity_window_admission"
    assert "retry_owner" not in retryable[0].payload
    assert (
        retryable[0].payload.get("claim_builder_attempt_next_action_kind")
        != ClaimBuilderAttemptNextActionKind.DEFER_UNTIL_CAPACITY_RESET.value
    )


@pytest.mark.asyncio
async def test_capacity_owned_minute_limit_does_not_project_item_retryable_failed() -> (
    None
):
    execution_result = ExecutePreparedLlmDispatchAttemptResult(
        dispatch=_dispatch(),
        llm_result=LlmDispatchExecutionResult(
            status=LlmDispatchExecutionStatus.RETRYABLE_FAILED,
            finished_at=_finished_at(),
            error_kind="minute_limit",
            next_attempt_at=_finished_at() + timedelta(seconds=30),
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
    )
    repository = InMemoryFrontendWorkflowEventRepository()
    projection_writer = ProjectFrontendWorkflowEvent(
        projector=ClaimBuilderFrontendWorkflowEventProjector(),
        repository=repository,
    )

    await _execute(
        execution_result=execution_result,
        frontend_event_projection_writer=projection_writer,
    )

    retryable = [
        event
        for event in repository.events.values()
        if event.projection_type == "workflow_claim_builder_section_retryable_failed"
    ]
    capacity = [
        event
        for event in repository.events.values()
        if event.projection_type == "workflow_capacity_window_observed"
    ]
    assert len(retryable) == 0
    assert len(capacity) == 1


@pytest.mark.asyncio
async def test_projects_claim_builder_section_terminal_failed_event_once() -> None:
    repository = InMemoryFrontendWorkflowEventRepository()
    projection_writer = ProjectFrontendWorkflowEvent(
        projector=ClaimBuilderFrontendWorkflowEventProjector(),
        repository=repository,
    )

    await _execute(
        execution_result=_execution_result(LlmDispatchExecutionStatus.TERMINAL_FAILED),
        frontend_event_projection_writer=projection_writer,
    )

    terminal = [
        event
        for event in repository.events.values()
        if event.projection_type == "workflow_claim_builder_section_terminal_failed"
    ]
    assert len(terminal) == 1
    assert terminal[0].payload["source_unit_ref"] == "section-1"
    assert terminal[0].payload["retry_eligibility"] == "not_eligible"
    assert "terminal_reason_category" in terminal[0].payload


@pytest.mark.asyncio
async def test_reprojects_section_outcome_idempotently() -> None:
    repository = InMemoryFrontendWorkflowEventRepository()
    projection_writer = ProjectFrontendWorkflowEvent(
        projector=ClaimBuilderFrontendWorkflowEventProjector(),
        repository=repository,
    )

    _, _, _, workflow_unit_of_work, _ = await _execute(
        frontend_event_projection_writer=projection_writer,
    )
    persisted_outcome_event = workflow_unit_of_work.outbox.events[1]
    await projection_writer.execute(persisted_outcome_event)
    await projection_writer.execute(persisted_outcome_event)

    extracted = [
        event
        for event in repository.events.values()
        if event.projection_type == "workflow_claim_builder_section_extracted"
    ]
    assert len(extracted) == 1


def test_deferred_status_does_not_emit_deferred_canonical_event() -> None:
    assert (
        _event_type_for_status(LlmDispatchExecutionStatus.DEFERRED)
        is not KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SECTION_EXTRACTION_DEFERRED
    )


def test_outcome_handler_projects_after_canonical_outbox_append() -> None:
    source = inspect.getsource(HandleExecuteClaimBuilderSectionCommandHandler.execute)

    outcome_append_index = source.index("persisted_outcome_event =")
    outcome_projection_index = source.index(
        "frontend_event_projection_writer.execute(persisted_outcome_event)",
    )
    assert outcome_append_index < outcome_projection_index


@pytest.mark.asyncio
async def test_reprojects_capacity_observed_idempotently() -> None:
    repository = InMemoryFrontendWorkflowEventRepository()
    projection_writer = ProjectFrontendWorkflowEvent(
        projector=LlmProviderCapacityObservedFrontendWorkflowEventProjector(),
        repository=repository,
    )

    _, _, _, workflow_unit_of_work, _ = await _execute(
        frontend_event_projection_writer=projection_writer,
    )
    persisted_event = workflow_unit_of_work.outbox.events[0]
    await projection_writer.execute(persisted_event)
    await projection_writer.execute(persisted_event)

    assert len(repository.events) == 1


@pytest.mark.asyncio
async def test_no_capacity_observation_does_not_create_capacity_projection() -> None:
    repository = InMemoryFrontendWorkflowEventRepository()
    projection_writer = ProjectFrontendWorkflowEvent(
        projector=LlmProviderCapacityObservedFrontendWorkflowEventProjector(),
        repository=repository,
    )
    base_result = _execution_result()
    execution_result = ExecutePreparedLlmDispatchAttemptResult(
        dispatch=base_result.dispatch,
        llm_result=LlmDispatchExecutionResult(
            status=base_result.llm_result.status,
            finished_at=base_result.llm_result.finished_at,
            output_payload=base_result.llm_result.output_payload,
            capacity_observation=None,
        ),
        outcome_result=base_result.outcome_result,
        validation_metadata=base_result.validation_metadata,
    )

    await _execute(
        execution_result=execution_result,
        frontend_event_projection_writer=projection_writer,
    )

    assert repository.events == {}


@pytest.mark.asyncio
async def test_handler_without_projection_writer_preserves_existing_behavior() -> None:
    _, _, _, workflow_unit_of_work, _ = await _execute()

    assert tuple(event.event_type for event in workflow_unit_of_work.outbox.events) == (
        KnowledgeExtractionCanonicalEventType.LLM_PROVIDER_CAPACITY_OBSERVED.value,
        KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SECTION_EXTRACTED.value,
    )


def test_execute_handler_projects_after_canonical_outbox_append() -> None:
    source = inspect.getsource(HandleExecuteClaimBuilderSectionCommandHandler.execute)

    append_index = source.index("outbox.append_event")
    projection_index = source.index("frontend_event_projection_writer.execute")
    assert append_index < projection_index


def test_execute_handler_does_not_touch_live_state_or_capacity_reads_for_projection() -> (
    None
):
    source = inspect.getsource(HandleExecuteClaimBuilderSectionCommandHandler.execute)

    for forbidden_marker in (
        "live_state",
        "fetch_workbench",
        "drain",
        "workflow_runner",
        "frontend_workflow_events",
    ):
        assert forbidden_marker not in source


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
async def test_reconcile_command_propagates_claim_builder_prepare_origin_trace() -> (
    None
):
    base_command = _workflow_command()
    payload = dict(base_command.payload)
    payload["claim_builder_prepare_command_id"] = (
        "workflow-command:prepare-claim-builder-dispatch-batch:origin"
    )
    payload["claim_builder_prepare_idempotency_key"] = (
        "prepare-claim-builder-dispatch-batch:origin"
    )
    workflow_command = WorkflowCommand(
        command_id=base_command.command_id,
        command_type=base_command.command_type,
        workflow_run_id=base_command.workflow_run_id,
        idempotency_key=base_command.idempotency_key,
        payload=payload,
        status=base_command.status,
        run_after=base_command.run_after,
        created_at=base_command.created_at,
        updated_at=base_command.updated_at,
    )

    _, _, _, workflow_unit_of_work, _ = await _execute(
        workflow_command=workflow_command,
    )

    next_command = workflow_unit_of_work.command_log.pending_commands[0]
    assert next_command.payload["claim_builder_prepare_command_id"] == (
        "workflow-command:prepare-claim-builder-dispatch-batch:origin"
    )
    assert next_command.payload["claim_builder_prepare_idempotency_key"] == (
        "prepare-claim-builder-dispatch-batch:origin"
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
async def test_retryable_outcome_updates_retryable_progress() -> None:
    _, _, _, workflow_unit_of_work, draft_persistence = await _execute(
        execution_result=_execution_result(LlmDispatchExecutionStatus.RETRYABLE_FAILED),
    )

    snapshot = workflow_unit_of_work.progress_snapshots.snapshot
    assert snapshot is not None
    assert snapshot.retryable_failed_work_items == 1
    assert workflow_unit_of_work.outbox.events[1].event_type == (
        KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_SECTION_EXTRACTION_RETRYABLE_FAILED.value
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
            next_attempt_at=None,
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
                ClaimBuilderOutputValidationDecision.RETRY_EMPTY_CLAIMS_CHECK_MODEL.value
            ),
            "validation_failure_reason": (
                ClaimBuilderOutputValidationFailureReason.CLAIMS_EMPTY_RETRY_REQUIRED.value
            ),
            "validated_claim_count": 0,
            "claim_builder_attempt_next_action_kind": (
                ClaimBuilderAttemptNextActionKind.RETRY_EMPTY_CLAIMS_CHECK_MODEL.value
            ),
            "claim_builder_attempt_next_action_reason": (
                ClaimBuilderOutputValidationFailureReason.CLAIMS_EMPTY_RETRY_REQUIRED.value
            ),
            "claim_builder_attempt_next_model_strategy": (
                "EMPTY_CLAIMS_CHECK_MODEL_REQUIRED"
            ),
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
        ClaimBuilderOutputValidationDecision.RETRY_EMPTY_CLAIMS_CHECK_MODEL.value
    )
    assert workflow_unit_of_work.outbox.events[1].payload["retry_recommended"] is True
    assert (
        workflow_unit_of_work.outbox.events[1].payload[
            "claim_builder_attempt_next_action_kind"
        ]
        == ClaimBuilderAttemptNextActionKind.RETRY_EMPTY_CLAIMS_CHECK_MODEL.value
    )
    assert (
        workflow_unit_of_work.outbox.events[1].payload[
            "claim_builder_attempt_next_model_strategy"
        ]
        == "EMPTY_CLAIMS_CHECK_MODEL_REQUIRED"
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
    assert (
        snapshot.domain_counters[
            "claim_builder_empty_claims_check_retry_required_count"
        ]
        == 1
    )


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
            next_attempt_at=None,
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
            "claim_builder_attempt_outcome_kind": "RETRY_EMPTY_CLAIMS_CHECK_MODEL",
            "validation_decision": (
                ClaimBuilderOutputValidationDecision.RETRY_EMPTY_CLAIMS_CHECK_MODEL.value
            ),
            "validation_failure_reason": (
                ClaimBuilderOutputValidationFailureReason.CLAIMS_EMPTY_RETRY_REQUIRED.value
            ),
            "validated_claim_count": 0,
            "next_model_strategy": "EMPTY_CLAIMS_CHECK_MODEL_REQUIRED",
            "claim_builder_attempt_next_action_kind": (
                ClaimBuilderAttemptNextActionKind.RETRY_EMPTY_CLAIMS_CHECK_MODEL.value
            ),
            "claim_builder_attempt_next_action_reason": (
                ClaimBuilderOutputValidationFailureReason.CLAIMS_EMPTY_RETRY_REQUIRED.value
            ),
            "claim_builder_attempt_next_model_strategy": (
                "EMPTY_CLAIMS_CHECK_MODEL_REQUIRED"
            ),
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
        "EMPTY_CLAIMS_CHECK_MODEL_REQUIRED"
    )
    assert (
        workflow_unit_of_work.outbox.events[1].payload[
            "claim_builder_attempt_next_action_kind"
        ]
        == ClaimBuilderAttemptNextActionKind.RETRY_EMPTY_CLAIMS_CHECK_MODEL.value
    )
    assert (
        workflow_unit_of_work.outbox.events[1].payload[
            "claim_builder_should_persist_claims"
        ]
        is False
    )


def test_invalid_json_without_truncation_retries_same_model() -> None:
    validator = ClaimBuilderLlmDispatchOutputValidator(
        policy=ClaimBuilderOutputValidationPolicy(),
    )

    result = validator.validate(
        dispatch_payload=_dispatch().dispatch_payload,
        output_payload={"raw_text": '{"claims":['},
        llm_status=LlmDispatchExecutionStatus.SUCCEEDED,
        finished_at=_finished_at(),
        attempt_number=1,
    )

    assert result.status is LlmDispatchExecutionStatus.RETRYABLE_FAILED
    assert result.metadata["validation_decision"] == (
        ClaimBuilderOutputValidationDecision.RETRY_SAME_ROUTE.value
    )
    assert result.metadata["validation_failure_reason"] == (
        ClaimBuilderOutputValidationFailureReason.INVALID_JSON_RETRY_REQUIRED.value
    )
    assert result.metadata["claim_builder_attempt_next_action_kind"] == (
        ClaimBuilderAttemptNextActionKind.RETRY_SAME_ROUTE.value
    )
    assert result.metadata["claim_builder_attempt_next_model_strategy"] == "SAME_MODEL"
    assert result.metadata["claim_builder_should_persist_claims"] is False


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


def test_retry_same_route_metadata_uses_retry_same_route_next_action() -> None:
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
        ClaimBuilderAttemptNextActionKind.RETRY_SAME_ROUTE.value
    )
    assert result.metadata["claim_builder_attempt_next_model_strategy"] == "SAME_MODEL"
    assert result.metadata["claim_builder_should_persist_claims"] is False


@pytest.mark.asyncio
async def test_provider_request_too_large_maps_to_larger_input_retry_action() -> None:
    _, _, _, workflow_unit_of_work, draft_persistence = await _execute(
        execution_result=_execution_result(LlmDispatchExecutionStatus.RETRYABLE_FAILED),
    )

    del draft_persistence
    event_payload = workflow_unit_of_work.outbox.events[1].payload
    assert event_payload["error_kind"] == "provider_error"


@pytest.mark.asyncio
async def test_provider_minute_limit_maps_to_capacity_wait_action() -> None:
    execution_result = ExecutePreparedLlmDispatchAttemptResult(
        dispatch=_dispatch(),
        llm_result=LlmDispatchExecutionResult(
            status=LlmDispatchExecutionStatus.RETRYABLE_FAILED,
            finished_at=_finished_at(),
            error_kind="minute_limit",
            next_attempt_at=_finished_at() + timedelta(seconds=30),
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
    )

    _, _, _, workflow_unit_of_work, _ = await _execute(
        execution_result=execution_result,
    )

    event_payload = workflow_unit_of_work.outbox.events[1].payload
    assert event_payload["claim_builder_attempt_next_action_kind"] == (
        ClaimBuilderAttemptNextActionKind.DEFER_UNTIL_CAPACITY_RESET.value
    )
    assert event_payload["claim_builder_attempt_next_model_strategy"] == "SAME_MODEL"
    assert (
        event_payload["claim_builder_next_run_after"]
        == (_finished_at() + timedelta(seconds=30)).isoformat()
    )


@pytest.mark.asyncio
async def test_provider_request_too_large_maps_to_larger_input_retry_metadata() -> None:
    execution_result = ExecutePreparedLlmDispatchAttemptResult(
        dispatch=_dispatch(),
        llm_result=LlmDispatchExecutionResult(
            status=LlmDispatchExecutionStatus.RETRYABLE_FAILED,
            finished_at=_finished_at(),
            error_kind="request_too_large",
            next_attempt_at=None,
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
    )

    _, _, _, workflow_unit_of_work, _ = await _execute(
        execution_result=execution_result,
    )

    event_payload = workflow_unit_of_work.outbox.events[1].payload
    assert event_payload["claim_builder_attempt_next_action_kind"] == (
        ClaimBuilderAttemptNextActionKind.RETRY_LARGER_INPUT_LIMIT_MODEL.value
    )
    assert event_payload["claim_builder_attempt_next_model_strategy"] == (
        "LARGER_INPUT_LIMIT_MODEL_REQUIRED"
    )


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


def test_source_context_text_keeps_heading_path_for_validation() -> None:
    dispatch_payload = {
        "schedule_payload": {
            "provider_messages": [
                {
                    "role": "system",
                    "content": "system prompt",
                },
                {
                    "role": "user",
                    "content": (
                        "source_unit_ref: section-1\n"
                        "heading_path: ProductName: docs / Клиентский Telegram-бот\n\n"
                        "## Клиентский Telegram-бот\n\n"
                        "Клиентский Telegram-бот нужен для первого контакта."
                    ),
                },
            ],
        },
    }

    assert "ProductName" in _source_context_text(dispatch_payload)
    assert "Клиентский Telegram-бот нужен для первого контакта" in _source_context_text(
        dispatch_payload,
    )


def _rate_limited_capacity_payload() -> dict[str, object]:
    return {
        **_capacity_payload(),
        "remaining_minute_requests": 0,
        "remaining_minute_tokens": 0,
        "outcome_class": "rate_limited",
    }


@pytest.mark.asyncio
async def test_provider_rate_limit_emits_capacity_window_exhausted() -> None:
    result, _, _, workflow_unit_of_work, _ = await _execute(
        execution_result=_execution_result_with_capacity(
            _rate_limited_capacity_payload(),
        ),
    )

    del result
    exhausted_events = [
        event
        for event in workflow_unit_of_work.outbox.events
        if event.event_type
        == KnowledgeExtractionCanonicalEventType.CAPACITY_WINDOW_EXHAUSTED.value
    ]
    assert len(exhausted_events) == 1
    payload = exhausted_events[0].payload
    assert payload["reset_at"]
    assert payload["window_key"] == "groq:groq_org_primary:qwen/qwen3-32b"
    assert "minute_requests" in payload["exhausted_dimensions"]
    assert "next_attempt_at" not in payload
    assert "retry_owner" not in payload


@pytest.mark.asyncio
async def test_provider_rate_limit_may_emit_capacity_window_scheduled_wakeup() -> None:
    workflow_command = _workflow_command()
    payload = dict(workflow_command.payload)
    payload["scheduled_work_item_count"] = 3
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

    _, _, _, workflow_unit_of_work, _ = await _execute(
        workflow_command=workflow_command,
        execution_result=_execution_result_with_capacity(
            _rate_limited_capacity_payload(),
        ),
    )

    wakeup_events = [
        event
        for event in workflow_unit_of_work.outbox.events
        if event.event_type
        == KnowledgeExtractionCanonicalEventType.CAPACITY_WINDOW_SCHEDULED_WAKEUP.value
    ]
    assert len(wakeup_events) == 1
    wakeup_payload = wakeup_events[0].payload
    assert wakeup_payload["run_after"]
    assert wakeup_payload["reset_at"]
    assert wakeup_payload["wakeup_reason"] == "provider_minute_reset"
    assert "next_attempt_at" not in wakeup_payload
    assert "retry_owner" not in wakeup_payload


def _execution_result_with_capacity(
    capacity_payload: dict[str, object],
) -> ExecutePreparedLlmDispatchAttemptResult:
    return ExecutePreparedLlmDispatchAttemptResult(
        dispatch=_dispatch(),
        llm_result=LlmDispatchExecutionResult(
            status=LlmDispatchExecutionStatus.RETRYABLE_FAILED,
            finished_at=_finished_at(),
            error_kind="rate_limited",
            capacity_observation=capacity_payload,
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
    )
