from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID

import pytest

from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.interfaces.composition.prepare_llm_dispatch_batch import (
    PrepareLlmDispatchBatchCommand,
)
from src.interfaces.composition.start_llm_admitted_work_item_attempts import (
    StartedLlmAdmittedAttempt,
)
from src.contexts.capacity_admission_queue.application.capacity_window_admission_pass import (
    CapacityWindowAdmissionPassCommand,
)
from src.contexts.capacity_admission_queue.application.capacity_window_admission_result import (
    CapacityAdmissionAdmittedItemSummary,
    CapacityAdmissionDispatchContextSummary,
    CapacityAdmissionFrontendEventSummary,
    CapacityAdmissionLaneSummary,
    CapacityAdmissionProjectionLeaseSummary,
    CapacityAdmissionStartedAttemptSummary,
    CapacityWindowAdmissionLogEvent,
    CapacityWindowAdmissionPassResult,
)
from src.contexts.knowledge_workbench.application.sagas.capacity_admission_phase_mapping import (
    CLAIM_BUILDER_ADMISSION_PHASE_PROFILE,
    DRAFT_CLAIM_COMPACTION_ADMISSION_PHASE_PROFILE,
)
from src.contexts.knowledge_workbench.application.sagas.dispatch_knowledge_extraction_workflow_command import (
    COMMAND_HANDLER_NOT_IMPLEMENTED,
    DispatchKnowledgeExtractionWorkflowCommand,
    DispatchKnowledgeExtractionWorkflowCommandHandler,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalCommandType,
    operation_by_command_type,
)
from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_progress import (
    DraftClaimCompactionProgressSummary,
)
from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_reduction_models import (
    DraftClaimCompactionPlannerState,
)
from src.contexts.knowledge_workbench.extraction.application.policies.draft_claim_compaction_output_validator import (
    DraftClaimCompactionOutputValidator,
)
from src.contexts.knowledge_workbench.extraction.application.ports.draft_claim_compaction_reduction_state_repository_port import (
    DraftClaimCompactionApplyPersistenceResult,
    DraftClaimCompactionReductionStatePersistenceResult,
)
from src.contexts.knowledge_workbench.extraction.application.ports.draft_claim_observation_read_repository_port import (
    DraftClaimObservationReadModel,
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


def _now() -> datetime:
    return datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)


def _workflow_run_id() -> str:
    return "knowledge-extraction:source-document:project-1:abc"


def _document_ref() -> SourceDocumentRef:
    return SourceDocumentRef("source-document:project-1:abc")


def _workflow_command(
    command_type: KnowledgeExtractionCanonicalCommandType,
    *,
    payload: dict[str, object] | None = None,
) -> WorkflowCommand:
    if payload is None:
        payload = _default_payload_for_command(command_type)

    return WorkflowCommand(
        command_id=WorkflowCommandId(f"workflow-command:{command_type.value}"),
        command_type=command_type.value,
        workflow_run_id=_workflow_run_id(),
        idempotency_key=WorkflowIdempotencyKey(
            f"{command_type.value}:{_workflow_run_id()}"
        ),
        payload=payload,
        status=WorkflowCommandStatus.PENDING,
        run_after=_now(),
        created_at=_now(),
        updated_at=_now(),
    )


def _default_payload_for_command(
    command_type: KnowledgeExtractionCanonicalCommandType,
) -> dict[str, object]:
    if (
        command_type
        is KnowledgeExtractionCanonicalCommandType.SCHEDULE_CLAIM_BUILDER_SECTION_WORK
    ):
        return {
            "workflow_run_id": _workflow_run_id(),
            "source_document_ref": _document_ref().value,
            "llm_dispatch_preparation": _dispatch_preparation(),
        }

    if (
        command_type
        is KnowledgeExtractionCanonicalCommandType.PREPARE_CLAIM_BUILDER_DISPATCH_BATCH
    ):
        return {
            "workflow_run_id": _workflow_run_id(),
            "scheduled_work_item_count": 1,
            "llm_dispatch_preparation": _dispatch_preparation(),
        }

    return {"workflow_run_id": _workflow_run_id()}


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
                "remaining_minute_requests": 1,
                "remaining_minute_tokens": 7000,
                "remaining_daily_requests": 100,
                "remaining_daily_tokens": 50000,
            },
        ),
        "active_model_ref": "qwen/qwen3-32b",
        "requested_items": 1,
        "worker_ref": "worker-1",
        "lease_token_prefix": "lease-prefix",
        "lease_ttl_seconds": 300,
    }


def _unknown_workflow_command() -> WorkflowCommand:
    return WorkflowCommand(
        command_id=WorkflowCommandId("workflow-command:unknown"),
        command_type="UnknownCommand",
        workflow_run_id=_workflow_run_id(),
        idempotency_key=WorkflowIdempotencyKey("unknown-command"),
        payload={"workflow_run_id": _workflow_run_id()},
        status=WorkflowCommandStatus.PENDING,
        run_after=_now(),
        created_at=_now(),
        updated_at=_now(),
    )


def _source_unit() -> SourceUnit:
    return SourceUnit(
        unit_ref=SourceUnitRef(f"{_document_ref().value}.unit.0"),
        document_ref=_document_ref(),
        unit_kind=SourceUnitKind.SECTION,
        text=SourceUnitText("# Unit\\n\\nBody"),
        heading_path=HeadingPath(("Unit",)),
        lineage=SourceUnitLineage(),
        ordinal=0,
        created_at=_now(),
    )


@dataclass(slots=True)
class FakeSourceManagementRepository:
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
        del units

    async def list_source_units_for_document(
        self,
        document_ref: SourceDocumentRef,
    ) -> tuple[SourceUnit, ...]:
        assert document_ref == _document_ref()
        return (_source_unit(),)

    async def load_source_unit(
        self,
        unit_ref: SourceUnitRef,
    ) -> SourceUnit | None:
        del unit_ref
        return _source_unit()


@dataclass(slots=True)
class FakeWorkItemSchedulingRepository:
    saved_count: int = 0

    async def get_work_item(self, work_item_id: str) -> WorkItem | None:
        del work_item_id
        return None

    async def get_schedule_payload_hash(self, work_item_id: str) -> str | None:
        del work_item_id
        return None

    async def save_scheduled_work_item(
        self,
        *,
        item: WorkItem,
        idempotency_key: str,
        payload_hash: str,
        payload: object,
    ) -> None:
        del item, idempotency_key, payload_hash, payload
        self.saved_count += 1


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
        return _workflow_command(
            KnowledgeExtractionCanonicalCommandType.SCHEDULE_CLAIM_BUILDER_SECTION_WORK
        )

    async def list_pending_commands(
        self,
        *,
        workflow_run_id: str,
        limit: int,
    ) -> tuple[WorkflowCommand, ...]:
        del workflow_run_id, limit
        return ()


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
        raise AssertionError("dispatcher must not own transaction commit")

    async def rollback(self) -> None:
        raise AssertionError("dispatcher must not own transaction rollback")


@pytest.mark.asyncio
async def test_dispatches_schedule_claim_builder_section_work_to_existing_handler() -> (
    None
):
    source_repository = FakeSourceManagementRepository()
    scheduling_repository = FakeWorkItemSchedulingRepository()
    workflow_unit_of_work = FakeWorkflowRuntimeUnitOfWork()

    result = await DispatchKnowledgeExtractionWorkflowCommandHandler().execute(
        DispatchKnowledgeExtractionWorkflowCommand(
            workflow_command=_workflow_command(
                KnowledgeExtractionCanonicalCommandType.SCHEDULE_CLAIM_BUILDER_SECTION_WORK
            )
        ),
        source_unit_repository=source_repository,
        knowledge_unit_of_work=scheduling_repository,
        workflow_unit_of_work=workflow_unit_of_work,
    )

    operation = operation_by_command_type(
        KnowledgeExtractionCanonicalCommandType.SCHEDULE_CLAIM_BUILDER_SECTION_WORK
    )
    assert result.dispatched is True
    assert result.operation_key == operation.operation_key
    assert result.phase == operation.phase.value
    assert result.handler_name == "HandleScheduleClaimBuilderSectionWorkCommandHandler"
    assert scheduling_repository.saved_count == 1


@dataclass(slots=True)
class FakeAttemptResult:
    started_attempts: tuple[StartedLlmAdmittedAttempt, ...]


@dataclass(slots=True)
class FakeAllocation:
    provider: str = "groq"
    account_ref: str = "groq_org_primary"
    model_ref: str = "qwen/qwen3-32b"

    def to_payload(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "account_ref": self.account_ref,
            "model_ref": self.model_ref,
        }


@dataclass(slots=True)
class FakeLeasedItem:
    schedule_payload: dict[str, object]
    allocation: FakeAllocation
    selection_kind: str = "fresh"

    def admitted_schedule_payload(self) -> dict[str, object]:
        return dict(self.schedule_payload)


@dataclass(slots=True)
class FakeLeaseResult:
    leased: tuple[FakeLeasedItem, ...]


@dataclass(slots=True)
class FakePrepareResult:
    lease_result: FakeLeaseResult
    attempt_result: FakeAttemptResult
    capacity_retry_at: datetime | None = None
    input_size_preflight_decision: str = "USE_ACTIVE_MODEL"
    input_size_preflight_reason: str = (
        "estimated prompt tokens fit active model input limit"
    )
    input_size_preflight_active_model_ref: str | None = "qwen/qwen3-32b"
    source_split_required: bool = False
    affected_work_item_refs: tuple[str, ...] = ()
    source_unit_refs: tuple[str, ...] = ()


@dataclass(slots=True)
class FakePrepareLlmDispatchBatch:
    calls: list[PrepareLlmDispatchBatchCommand] = field(default_factory=list)
    capacity_retry_at: datetime | None = None

    async def execute(self, command: PrepareLlmDispatchBatchCommand) -> object:
        self.calls.append(command)
        model_ref = command.active_model_ref or "qwen/qwen3-32b"
        allocation = FakeAllocation(model_ref=model_ref)
        schedule_payload: dict[str, object] = {
            "workflow_run_id": _workflow_run_id(),
            "source_document_ref": _document_ref().value,
            "source_unit_ref": f"{_document_ref().value}.unit.0",
            "group_ref": "group-1",
            "batch_ref": "batch-1",
            "round_index": 0,
            "expected_output_kind": "compacted_claims",
            "source_claim_refs": ["claim-a", "claim-b"],
            "left_node_ref": "raw:workflow-1:group-1:claim-a",
            "right_node_ref": "raw:workflow-1:group-1:claim-b",
        }
        return FakePrepareResult(
            lease_result=FakeLeaseResult(
                leased=(
                    FakeLeasedItem(
                        schedule_payload=schedule_payload,
                        allocation=allocation,
                    ),
                ),
            ),
            capacity_retry_at=self.capacity_retry_at,
            attempt_result=FakeAttemptResult(
                started_attempts=(
                    StartedLlmAdmittedAttempt(
                        attempt_id="work-1:attempt:1",
                        work_item_id="work-1",
                        attempt_number=1,
                        dispatch_payload={
                            "work_item_id": "work-1",
                            "schedule_payload": schedule_payload,
                            "llm_allocation": allocation.to_payload(),
                        },
                    ),
                ),
            ),
        )


@pytest.mark.asyncio
async def test_dispatches_prepare_claim_builder_dispatch_batch_to_existing_handler() -> (
    None
):
    prepare = FakePrepareLlmDispatchBatch()
    workflow_unit_of_work = FakeWorkflowRuntimeUnitOfWork()

    result = await DispatchKnowledgeExtractionWorkflowCommandHandler().execute(
        DispatchKnowledgeExtractionWorkflowCommand(
            workflow_command=_workflow_command(
                KnowledgeExtractionCanonicalCommandType.PREPARE_CLAIM_BUILDER_DISPATCH_BATCH
            )
        ),
        source_unit_repository=FakeSourceManagementRepository(),
        knowledge_unit_of_work=FakeWorkItemSchedulingRepository(),
        workflow_unit_of_work=workflow_unit_of_work,
        prepare_llm_dispatch_batch=prepare,
    )

    operation = operation_by_command_type(
        KnowledgeExtractionCanonicalCommandType.PREPARE_CLAIM_BUILDER_DISPATCH_BATCH
    )
    assert result.dispatched is True
    assert result.blocked_reason is None
    assert result.operation_key == operation.operation_key
    assert result.phase == operation.phase.value
    assert result.handler_name == "HandlePrepareClaimBuilderDispatchBatchCommandHandler"
    assert len(prepare.calls) == 1
    assert tuple(
        command.command_type
        for command in workflow_unit_of_work.command_log.pending_commands
    ) == (KnowledgeExtractionCanonicalCommandType.EXECUTE_CLAIM_BUILDER_SECTION.value,)


@pytest.mark.asyncio
async def test_known_unimplemented_execute_claim_builder_section_returns_blocked() -> (
    None
):
    result = await DispatchKnowledgeExtractionWorkflowCommandHandler().execute(
        DispatchKnowledgeExtractionWorkflowCommand(
            workflow_command=_workflow_command(
                KnowledgeExtractionCanonicalCommandType.EXECUTE_CLAIM_BUILDER_SECTION
            )
        ),
        source_unit_repository=FakeSourceManagementRepository(),
        knowledge_unit_of_work=FakeWorkItemSchedulingRepository(),
        workflow_unit_of_work=FakeWorkflowRuntimeUnitOfWork(),
    )

    operation = operation_by_command_type(
        KnowledgeExtractionCanonicalCommandType.EXECUTE_CLAIM_BUILDER_SECTION
    )
    assert result.dispatched is False
    assert result.blocked_reason == COMMAND_HANDLER_NOT_IMPLEMENTED
    assert result.operation_key == operation.operation_key
    assert result.phase == operation.phase.value


@dataclass(slots=True)
class FakeDraftClaimCompactionPlanRepository:
    pass


@dataclass(slots=True)
class FakeDraftClaimObservationReadRepository:
    requested_refs: list[tuple[str, ...]] = field(default_factory=list)

    async def list_by_observation_refs(
        self,
        *,
        observation_refs: tuple[str, ...],
    ) -> tuple[DraftClaimObservationReadModel, ...]:
        self.requested_refs.append(observation_refs)
        return tuple(
            _raw_claim(observation_ref) for observation_ref in observation_refs
        )


@dataclass(slots=True)
class FakeDraftClaimCompactionReductionStateRepository:
    applied_compacted_claims: list[object] = field(default_factory=list)

    async def summarize_compaction_progress(
        self,
        *,
        workflow_run_id: str,
    ) -> DraftClaimCompactionProgressSummary:
        return DraftClaimCompactionProgressSummary(
            workflow_run_id=workflow_run_id,
            group_count=1,
            done_group_count=0,
            waiting_user_model_choice_group_count=0,
            active_group_count=1,
            active_node_count=2,
            pending_comparison_count=1,
        )

    async def load_planner_state(
        self,
        *,
        workflow_run_id: str,
        group_ref: str,
    ) -> DraftClaimCompactionPlannerState | None:
        del workflow_run_id, group_ref
        return DraftClaimCompactionPlannerState(cluster_ref="group-1", nodes=())

    async def seed_initial_planner_state(
        self,
        *,
        workflow_run_id: str,
        group_ref: str,
        raw_nodes,
        created_at: datetime,
    ) -> DraftClaimCompactionReductionStatePersistenceResult:
        del workflow_run_id, group_ref, raw_nodes, created_at
        raise AssertionError("seed_initial_planner_state must not be called")

    async def apply_compacted_claims_result(
        self,
        *,
        workflow_run_id: str,
        group_ref: str,
        batch_ref: str,
        work_item_id: str,
        round_index: int,
        compacted_claims,
        compared_node_refs,
        created_at: datetime,
    ) -> DraftClaimCompactionApplyPersistenceResult:
        del workflow_run_id, group_ref, batch_ref, work_item_id
        del round_index, compared_node_refs, created_at
        self.applied_compacted_claims.append(compacted_claims)
        return _apply_persistence_result()

    async def apply_reduced_rewrite_result(
        self,
        *,
        workflow_run_id: str,
        group_ref: str,
        batch_ref: str,
        work_item_id: str,
        round_index: int,
        source_node_refs,
        rewrite,
        created_at: datetime,
    ) -> DraftClaimCompactionApplyPersistenceResult:
        del workflow_run_id, group_ref, batch_ref, work_item_id
        del round_index, source_node_refs, rewrite, created_at
        return _apply_persistence_result()


@pytest.mark.asyncio
async def test_cluster_draft_claims_requires_reduction_state_repository() -> None:
    result = await DispatchKnowledgeExtractionWorkflowCommandHandler().execute(
        DispatchKnowledgeExtractionWorkflowCommand(
            workflow_command=_workflow_command(
                KnowledgeExtractionCanonicalCommandType.CLUSTER_DRAFT_CLAIMS
            )
        ),
        source_unit_repository=FakeSourceManagementRepository(),
        knowledge_unit_of_work=FakeWorkItemSchedulingRepository(),
        workflow_unit_of_work=FakeWorkflowRuntimeUnitOfWork(),
        draft_claim_compaction_plan_repository=FakeDraftClaimCompactionPlanRepository(),
    )

    operation = operation_by_command_type(
        KnowledgeExtractionCanonicalCommandType.CLUSTER_DRAFT_CLAIMS
    )
    assert result.dispatched is False
    assert result.blocked_reason == COMMAND_HANDLER_NOT_IMPLEMENTED
    assert result.operation_key == operation.operation_key
    assert result.phase == operation.phase.value


def _raw_claim(observation_ref: str) -> DraftClaimObservationReadModel:
    return DraftClaimObservationReadModel(
        observation_ref=observation_ref,
        source_unit_ref="source-unit-1",
        claim=f"Raw claim {observation_ref}",
        granularity="atomic",
        possible_questions=(f"Q {observation_ref}",),
        exclusion_scope="not X",
        evidence_block=f"Evidence {observation_ref}",
        workflow_run_id=None,
        stage_run_id=None,
        work_item_id=None,
        work_item_attempt_id=None,
        llm_task_id=None,
        llm_attempt_id=None,
        prompt_id=None,
        prompt_version=None,
        claim_index=None,
        created_at=_now(),
    )


@pytest.mark.asyncio
async def test_unknown_command_type_raises_value_error() -> None:
    with pytest.raises(ValueError, match="unknown knowledge extraction command type"):
        await DispatchKnowledgeExtractionWorkflowCommandHandler().execute(
            DispatchKnowledgeExtractionWorkflowCommand(
                workflow_command=_unknown_workflow_command()
            ),
            source_unit_repository=FakeSourceManagementRepository(),
            knowledge_unit_of_work=FakeWorkItemSchedulingRepository(),
            workflow_unit_of_work=FakeWorkflowRuntimeUnitOfWork(),
        )


@pytest.mark.asyncio
async def test_apply_draft_claim_compaction_result_requires_reduction_state_repository() -> (
    None
):
    result = await DispatchKnowledgeExtractionWorkflowCommandHandler().execute(
        DispatchKnowledgeExtractionWorkflowCommand(
            workflow_command=_workflow_command(
                KnowledgeExtractionCanonicalCommandType.APPLY_DRAFT_CLAIM_COMPACTION_RESULT,
                payload=_apply_result_payload(),
            )
        ),
        source_unit_repository=FakeSourceManagementRepository(),
        knowledge_unit_of_work=FakeWorkItemSchedulingRepository(),
        workflow_unit_of_work=FakeWorkflowRuntimeUnitOfWork(),
    )

    assert result.dispatched is False
    assert result.blocked_reason == COMMAND_HANDLER_NOT_IMPLEMENTED


@pytest.mark.asyncio
async def test_apply_draft_claim_compaction_result_requires_raw_claim_read_repository() -> (
    None
):
    result = await DispatchKnowledgeExtractionWorkflowCommandHandler().execute(
        DispatchKnowledgeExtractionWorkflowCommand(
            workflow_command=_workflow_command(
                KnowledgeExtractionCanonicalCommandType.APPLY_DRAFT_CLAIM_COMPACTION_RESULT,
                payload=_apply_result_payload(),
            )
        ),
        source_unit_repository=FakeSourceManagementRepository(),
        knowledge_unit_of_work=FakeWorkItemSchedulingRepository(),
        workflow_unit_of_work=FakeWorkflowRuntimeUnitOfWork(),
        draft_claim_compaction_reduction_state_repository=(
            FakeDraftClaimCompactionReductionStateRepository()
        ),
    )

    assert result.dispatched is False
    assert result.blocked_reason == COMMAND_HANDLER_NOT_IMPLEMENTED


@pytest.mark.asyncio
async def test_apply_draft_claim_compaction_result_dispatches_when_dependencies_exist() -> (
    None
):
    repository = FakeDraftClaimCompactionReductionStateRepository()
    read_repository = FakeDraftClaimObservationReadRepository()

    result = await DispatchKnowledgeExtractionWorkflowCommandHandler().execute(
        DispatchKnowledgeExtractionWorkflowCommand(
            workflow_command=_workflow_command(
                KnowledgeExtractionCanonicalCommandType.APPLY_DRAFT_CLAIM_COMPACTION_RESULT,
                payload=_apply_result_payload(),
            )
        ),
        source_unit_repository=FakeSourceManagementRepository(),
        knowledge_unit_of_work=FakeWorkItemSchedulingRepository(),
        workflow_unit_of_work=FakeWorkflowRuntimeUnitOfWork(),
        draft_claim_compaction_reduction_state_repository=repository,
        draft_claim_observation_read_repository=read_repository,
        execute_prepared_llm_dispatch_attempt=(
            FakeDraftClaimCompactionWorkItemCompletion()
        ),
    )

    assert result.dispatched is True
    assert result.handler_name == "HandleApplyDraftClaimCompactionResultCommandHandler"
    assert read_repository.requested_refs == [("claim-a", "claim-b")]
    compacted_claim = repository.applied_compacted_claims[0][0]
    assert compacted_claim.possible_questions == ("Q claim-a", "Q claim-b")


def _apply_result_payload() -> dict[str, object]:
    return {
        "workflow_run_id": _workflow_run_id(),
        "group_ref": "group-1",
        "batch_ref": "batch-1",
        "work_item_id": "work-item-1",
        "round_index": 0,
        "lease_token": "lease-token-1",
        "output_kind": "compacted_claims",
        "left_node_ref": "raw:workflow-1:group-1:claim-a",
        "right_node_ref": "raw:workflow-1:group-1:claim-b",
        "compacted_claims": [
            {
                "key": "refund_support",
                "claim": "Product supports refunds.",
                "claim_kind": "capability",
                "source_claim_refs": ["claim-a", "claim-b"],
                "triples": [
                    {
                        "subject": "Product",
                        "predicate": "has_capability",
                        "object": "refunds",
                        "qualifiers": [],
                    }
                ],
                "merge_decision": "merged",
            }
        ],
        "reduced_rewrite": None,
    }


def _apply_persistence_result() -> DraftClaimCompactionApplyPersistenceResult:
    return DraftClaimCompactionApplyPersistenceResult(
        inserted_node_count=1,
        updated_node_count=2,
        inserted_source_count=2,
        inserted_comparison_count=1,
        superseded_node_count=2,
        already_exists_count=0,
    )


@pytest.mark.asyncio
async def test_reconcile_draft_claim_compaction_progress_requires_reduction_state_repository() -> (
    None
):
    result = await DispatchKnowledgeExtractionWorkflowCommandHandler().execute(
        DispatchKnowledgeExtractionWorkflowCommand(
            workflow_command=_workflow_command(
                KnowledgeExtractionCanonicalCommandType.RECONCILE_DRAFT_CLAIM_COMPACTION_PROGRESS
            )
        ),
        source_unit_repository=FakeSourceManagementRepository(),
        knowledge_unit_of_work=FakeWorkItemSchedulingRepository(),
        workflow_unit_of_work=FakeWorkflowRuntimeUnitOfWork(),
    )

    assert result.dispatched is False
    assert result.blocked_reason == COMMAND_HANDLER_NOT_IMPLEMENTED


@pytest.mark.asyncio
async def test_reconcile_draft_claim_compaction_progress_dispatches_when_dependency_exists() -> (
    None
):
    result = await DispatchKnowledgeExtractionWorkflowCommandHandler().execute(
        DispatchKnowledgeExtractionWorkflowCommand(
            workflow_command=_workflow_command(
                KnowledgeExtractionCanonicalCommandType.RECONCILE_DRAFT_CLAIM_COMPACTION_PROGRESS
            )
        ),
        source_unit_repository=FakeSourceManagementRepository(),
        knowledge_unit_of_work=FakeWorkItemSchedulingRepository(),
        workflow_unit_of_work=FakeWorkflowRuntimeUnitOfWork(),
        draft_claim_compaction_reduction_state_repository=(
            FakeDraftClaimCompactionReductionStateRepository()
        ),
    )

    assert result.dispatched is True
    assert (
        result.handler_name
        == "HandleReconcileDraftClaimCompactionProgressCommandHandler"
    )


def _draft_claim_compaction_dispatch_payload() -> dict[str, object]:
    return {
        "workflow_run_id": _workflow_run_id(),
        "scheduled_work_item_count": 1,
        "llm_dispatch_preparation": {
            "profile": {
                "profile_id": "draft_claim_compaction",
                "estimated_prompt_tokens": 90000,
                "estimated_completion_tokens": 4000,
                "estimated_requests": 1,
            },
            "account_capacities": (
                {
                    "provider": "groq",
                    "account_ref": "groq_org_primary",
                    "model_ref": "openai/gpt-oss-120b",
                    "remaining_minute_requests": 1,
                    "remaining_minute_tokens": 100000,
                    "remaining_daily_requests": 100,
                    "remaining_daily_tokens": 1000000,
                },
            ),
            "active_model_ref": "openai/gpt-oss-120b",
            "requested_items": 1,
            "worker_ref": "knowledge-workbench-draft-claim-compaction-dispatch",
            "lease_token_prefix": f"draft-claim-compaction-dispatch:{_workflow_run_id()}",
            "lease_ttl_seconds": 300,
        },
    }


@pytest.mark.asyncio
async def test_prepare_draft_claim_compaction_dispatch_batch_requires_prepare_dependency() -> (
    None
):
    result = await DispatchKnowledgeExtractionWorkflowCommandHandler().execute(
        DispatchKnowledgeExtractionWorkflowCommand(
            workflow_command=_workflow_command(
                KnowledgeExtractionCanonicalCommandType.PREPARE_DRAFT_CLAIM_COMPACTION_DISPATCH_BATCH,
                payload=_draft_claim_compaction_dispatch_payload(),
            )
        ),
        source_unit_repository=FakeSourceManagementRepository(),
        knowledge_unit_of_work=FakeWorkItemSchedulingRepository(),
        workflow_unit_of_work=FakeWorkflowRuntimeUnitOfWork(),
    )

    assert result.dispatched is False
    assert result.blocked_reason == COMMAND_HANDLER_NOT_IMPLEMENTED


@pytest.mark.asyncio
async def test_prepare_draft_claim_compaction_dispatch_batch_dispatches_when_dependency_exists() -> (
    None
):
    prepare = FakePrepareLlmDispatchBatch()
    result = await DispatchKnowledgeExtractionWorkflowCommandHandler().execute(
        DispatchKnowledgeExtractionWorkflowCommand(
            workflow_command=_workflow_command(
                KnowledgeExtractionCanonicalCommandType.PREPARE_DRAFT_CLAIM_COMPACTION_DISPATCH_BATCH,
                payload=_draft_claim_compaction_dispatch_payload(),
            )
        ),
        source_unit_repository=FakeSourceManagementRepository(),
        knowledge_unit_of_work=FakeWorkItemSchedulingRepository(),
        workflow_unit_of_work=FakeWorkflowRuntimeUnitOfWork(),
        prepare_llm_dispatch_batch=prepare,
    )

    assert result.dispatched is True
    assert (
        result.handler_name
        == "HandlePrepareDraftClaimCompactionDispatchBatchCommandHandler"
    )
    assert len(prepare.calls) == 1
    assert (
        prepare.calls[0].work_kind.value == "knowledge_workbench.draft_claim_compaction"
    )
    assert prepare.calls[0].active_model_ref == "openai/gpt-oss-120b"


def _execute_draft_claim_compaction_payload() -> dict[str, object]:
    return {
        "workflow_run_id": _workflow_run_id(),
        "dispatch_attempt_id": "attempt-1",
        "work_item_id": "work-item-1",
        "group_ref": "group-1",
        "batch_ref": "batch-1",
        "round_index": 0,
        "expected_output_kind": "compacted_claims",
        "source_claim_refs": ["claim-a", "claim-b"],
        "left_node_ref": "raw:workflow-1:group-1:claim-a",
        "right_node_ref": "raw:workflow-1:group-1:claim-b",
    }


@dataclass(slots=True)
class FakeExecutePreparedLlmDispatchAttempt:
    calls: int = 0

    async def execute(self, command) -> object:
        del command
        self.calls += 1
        raise RuntimeError("fake execute should not be reached in wiring block tests")


@dataclass(slots=True)
class FakeCapacityObservationRepository:
    observations: list[object] = field(default_factory=list)

    async def record_observation(self, observation) -> None:
        self.observations.append(observation)


@dataclass(slots=True)
class FakeDraftClaimCompactionWorkItemCompletion:
    completed_work_item_ids: list[str] = field(default_factory=list)

    async def complete_work_item_after_domain_apply(
        self,
        *,
        work_item_id: str,
        lease_token: object,
    ) -> object:
        del lease_token
        self.completed_work_item_ids.append(work_item_id)
        return object()


async def _dispatch_execute_draft_claim_compaction(
    *,
    execute_dependency: FakeExecutePreparedLlmDispatchAttempt | None,
    capacity_repository: FakeCapacityObservationRepository | None,
    validator: DraftClaimCompactionOutputValidator | None,
):
    return await DispatchKnowledgeExtractionWorkflowCommandHandler().execute(
        DispatchKnowledgeExtractionWorkflowCommand(
            workflow_command=_workflow_command(
                KnowledgeExtractionCanonicalCommandType.EXECUTE_DRAFT_CLAIM_COMPACTION,
                payload=_execute_draft_claim_compaction_payload(),
            )
        ),
        source_unit_repository=FakeSourceManagementRepository(),
        knowledge_unit_of_work=FakeWorkItemSchedulingRepository(),
        workflow_unit_of_work=FakeWorkflowRuntimeUnitOfWork(),
        execute_prepared_llm_dispatch_attempt=execute_dependency,
        capacity_observation_repository=capacity_repository,
        draft_claim_compaction_output_validator=validator,
    )


@pytest.mark.asyncio
async def test_execute_draft_claim_compaction_blocks_when_execute_dependency_missing() -> (
    None
):
    result = await _dispatch_execute_draft_claim_compaction(
        execute_dependency=None,
        capacity_repository=FakeCapacityObservationRepository(),
        validator=DraftClaimCompactionOutputValidator(),
    )

    assert result.dispatched is False
    assert result.blocked_reason == COMMAND_HANDLER_NOT_IMPLEMENTED


@pytest.mark.asyncio
async def test_execute_draft_claim_compaction_blocks_when_capacity_repository_missing() -> (
    None
):
    result = await _dispatch_execute_draft_claim_compaction(
        execute_dependency=FakeExecutePreparedLlmDispatchAttempt(),
        capacity_repository=None,
        validator=DraftClaimCompactionOutputValidator(),
    )

    assert result.dispatched is False
    assert result.blocked_reason == COMMAND_HANDLER_NOT_IMPLEMENTED


@pytest.mark.asyncio
async def test_execute_draft_claim_compaction_blocks_when_validator_missing() -> None:
    result = await _dispatch_execute_draft_claim_compaction(
        execute_dependency=FakeExecutePreparedLlmDispatchAttempt(),
        capacity_repository=FakeCapacityObservationRepository(),
        validator=None,
    )

    assert result.dispatched is False
    assert result.blocked_reason == COMMAND_HANDLER_NOT_IMPLEMENTED


@pytest.mark.asyncio
async def test_execute_draft_claim_compaction_no_implemented_unwired_gap() -> None:
    execute_dependency = FakeExecutePreparedLlmDispatchAttempt()

    with pytest.raises(RuntimeError, match="fake execute should not be reached"):
        await _dispatch_execute_draft_claim_compaction(
            execute_dependency=execute_dependency,
            capacity_repository=FakeCapacityObservationRepository(),
            validator=DraftClaimCompactionOutputValidator(),
        )

    assert execute_dependency.calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "command_type",
    (
        KnowledgeExtractionCanonicalCommandType.OPEN_DRAFT_CLAIM_CURATION_WORKSPACE,
        KnowledgeExtractionCanonicalCommandType.PUBLISH_DRAFT_CLAIM_CURATION_WORKSPACE,
    ),
)
async def test_curation_commands_block_without_required_dependencies(
    command_type: KnowledgeExtractionCanonicalCommandType,
) -> None:
    result = await DispatchKnowledgeExtractionWorkflowCommandHandler().execute(
        DispatchKnowledgeExtractionWorkflowCommand(
            workflow_command=_workflow_command(command_type)
        ),
        source_unit_repository=FakeSourceManagementRepository(),
        knowledge_unit_of_work=FakeWorkItemSchedulingRepository(),
        workflow_unit_of_work=FakeWorkflowRuntimeUnitOfWork(),
    )

    assert result.dispatched is False
    assert result.blocked_reason == COMMAND_HANDLER_NOT_IMPLEMENTED


@pytest.mark.asyncio
async def test_dispatch_repairs_claim_builder_prepare_command_without_dispatch_preparation() -> (
    None
):
    prepare = FakePrepareLlmDispatchBatch()
    workflow_unit_of_work = FakeWorkflowRuntimeUnitOfWork()

    result = await DispatchKnowledgeExtractionWorkflowCommandHandler().execute(
        DispatchKnowledgeExtractionWorkflowCommand(
            workflow_command=_workflow_command(
                KnowledgeExtractionCanonicalCommandType.PREPARE_CLAIM_BUILDER_DISPATCH_BATCH,
                payload={
                    "workflow_run_id": _workflow_run_id(),
                    "source_document_ref": _document_ref().value,
                    "scheduled_work_item_count": 2,
                },
            )
        ),
        source_unit_repository=FakeSourceManagementRepository(),
        knowledge_unit_of_work=FakeWorkItemSchedulingRepository(),
        workflow_unit_of_work=workflow_unit_of_work,
        prepare_llm_dispatch_batch=prepare,
    )

    assert result.dispatched is True
    assert result.blocked_reason is None
    assert len(prepare.calls) == 1
    assert prepare.calls[0].active_model_ref == "qwen/qwen3-32b"
    assert prepare.calls[0].requested_items == 2
    assert prepare.calls[0].worker.value == (
        "knowledge-workbench-claim-builder-dispatch"
    )


@pytest.mark.asyncio
async def test_dispatch_repairs_compaction_prepare_command_without_dispatch_preparation() -> (
    None
):
    prepare = FakePrepareLlmDispatchBatch()

    result = await DispatchKnowledgeExtractionWorkflowCommandHandler().execute(
        DispatchKnowledgeExtractionWorkflowCommand(
            workflow_command=_workflow_command(
                KnowledgeExtractionCanonicalCommandType.PREPARE_DRAFT_CLAIM_COMPACTION_DISPATCH_BATCH,
                payload={
                    "workflow_run_id": _workflow_run_id(),
                    "scheduled_work_item_count": 2,
                },
            )
        ),
        source_unit_repository=FakeSourceManagementRepository(),
        knowledge_unit_of_work=FakeWorkItemSchedulingRepository(),
        workflow_unit_of_work=FakeWorkflowRuntimeUnitOfWork(),
        prepare_llm_dispatch_batch=prepare,
    )

    assert result.dispatched is True
    assert result.blocked_reason is None
    assert len(prepare.calls) == 1
    assert prepare.calls[0].active_model_ref == "openai/gpt-oss-120b"
    assert prepare.calls[0].requested_items == 2
    assert prepare.calls[0].worker.value == (
        "knowledge-workbench-draft-claim-compaction-dispatch"
    )


@pytest.mark.asyncio
async def test_generate_draft_claim_embeddings_passes_frontend_projection_writer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_execute(
        self: object, command: object, **dependencies: object
    ) -> object:
        del self, command
        captured.update(dependencies)
        from src.contexts.knowledge_workbench.application.sagas.handle_generate_draft_claim_embeddings_command import (
            HandleGenerateDraftClaimEmbeddingsResult,
        )
        from src.contexts.workflow_runtime.domain.value_objects.workflow_command_id import (
            WorkflowCommandId,
        )

        return HandleGenerateDraftClaimEmbeddingsResult(
            workflow_run_id=_workflow_run_id(),
            requested_embedding_count=0,
            persisted_embedding_count=0,
            appended_event_count=1,
            appended_next_command_count=1,
            completed_command_id=WorkflowCommandId("workflow-command:done"),
        )

    from src.contexts.knowledge_workbench.application.sagas import (
        handle_generate_draft_claim_embeddings_command as embedding_handler_module,
    )
    from src.contexts.knowledge_workbench.observability.application.projectors.project_frontend_workflow_event import (
        ProjectFrontendWorkflowEvent,
    )

    monkeypatch.setattr(
        embedding_handler_module.HandleGenerateDraftClaimEmbeddingsCommandHandler,
        "execute",
        fake_execute,
    )

    @dataclass(slots=True)
    class _FakeRepository:
        async def append(self, event: object) -> object:
            return event

    @dataclass(slots=True)
    class _FakeProjector:
        def project(self, event: object) -> None:
            del event
            return None

    projection_writer = ProjectFrontendWorkflowEvent(
        projector=_FakeProjector(),
        repository=_FakeRepository(),
    )

    await DispatchKnowledgeExtractionWorkflowCommandHandler().execute(
        DispatchKnowledgeExtractionWorkflowCommand(
            workflow_command=_workflow_command(
                KnowledgeExtractionCanonicalCommandType.GENERATE_DRAFT_CLAIM_EMBEDDINGS,
                payload={
                    "workflow_run_id": _workflow_run_id(),
                    "source_document_ref": "source-document:project-1:abc",
                },
            )
        ),
        source_unit_repository=FakeSourceManagementRepository(),
        knowledge_unit_of_work=FakeWorkItemSchedulingRepository(),
        workflow_unit_of_work=FakeWorkflowRuntimeUnitOfWork(),
        draft_claim_embedding_read_repository=object(),
        draft_claim_embedding_persistence=object(),
        embedding_generation_port=object(),
        embedding_model_id="sentence-transformers/all-MiniLM-L6-v2",
        embedding_dimensions=384,
        frontend_event_projection_writer=projection_writer,
    )

    assert captured["frontend_event_projection_writer"] is projection_writer


@pytest.mark.asyncio
async def test_cluster_draft_claims_passes_frontend_projection_writer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_execute(
        self: object, command: object, **dependencies: object
    ) -> object:
        del self, command
        captured.update(dependencies)
        from src.contexts.knowledge_workbench.application.sagas.handle_cluster_draft_claims_command import (
            HandleClusterDraftClaimsResult,
        )

        return HandleClusterDraftClaimsResult(
            workflow_run_id=_workflow_run_id(),
            candidate_edge_count=0,
            group_count=0,
            batch_count=0,
            scheduled_work_item_count=0,
            already_scheduled_work_item_count=0,
        )

    from src.contexts.knowledge_workbench.application.sagas import (
        handle_cluster_draft_claims_command as cluster_handler_module,
    )
    from src.contexts.knowledge_workbench.observability.application.projectors.project_frontend_workflow_event import (
        ProjectFrontendWorkflowEvent,
    )

    monkeypatch.setattr(
        cluster_handler_module.HandleClusterDraftClaimsCommandHandler,
        "execute",
        fake_execute,
    )

    @dataclass(slots=True)
    class _FakeRepository:
        async def append(self, event: object) -> object:
            return event

    @dataclass(slots=True)
    class _FakeProjector:
        def project(self, event: object) -> None:
            del event
            return None

    projection_writer = ProjectFrontendWorkflowEvent(
        projector=_FakeProjector(),
        repository=_FakeRepository(),
    )

    result = await DispatchKnowledgeExtractionWorkflowCommandHandler().execute(
        DispatchKnowledgeExtractionWorkflowCommand(
            workflow_command=_workflow_command(
                KnowledgeExtractionCanonicalCommandType.CLUSTER_DRAFT_CLAIMS,
                payload={
                    "workflow_run_id": _workflow_run_id(),
                    "embedding_model_id": "sentence-transformers/all-MiniLM-L6-v2",
                },
            )
        ),
        source_unit_repository=FakeSourceManagementRepository(),
        knowledge_unit_of_work=FakeWorkItemSchedulingRepository(),
        workflow_unit_of_work=FakeWorkflowRuntimeUnitOfWork(),
        draft_claim_compaction_plan_repository=FakeDraftClaimCompactionPlanRepository(),
        draft_claim_compaction_reduction_state_repository=(
            FakeDraftClaimCompactionReductionStateRepository()
        ),
        frontend_event_projection_writer=projection_writer,
    )

    assert captured["frontend_event_projection_writer"] is projection_writer
    assert result.dispatched is True
    assert result.blocked_reason is None


@dataclass(slots=True)
class FakeCapacityWindowAdmissionPass:
    result: CapacityWindowAdmissionPassResult
    calls: list[CapacityWindowAdmissionPassCommand] = field(default_factory=list)

    async def execute(self, command: CapacityWindowAdmissionPassCommand) -> object:
        self.calls.append(command)
        return self.result


def _claim_builder_admission_result() -> CapacityWindowAdmissionPassResult:
    lane = CapacityAdmissionLaneSummary(
        work_kind=CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.work_kind,
        provider="groq",
        account_ref="groq-account-1",
        model_ref="qwen/qwen3-32b",
    )
    projection_event_id = UUID("00000000-0000-0000-0000-000000000501")
    return CapacityWindowAdmissionPassResult(
        workflow_run_id=_workflow_run_id(),
        phase=CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.phase,
        operation_key=CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.operation_key,
        work_kind=CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.work_kind,
        lane=lane,
        admitted_items=(
            CapacityAdmissionAdmittedItemSummary(
                work_item_id="work-1",
                lane=lane,
                selection_kind="fresh",
                estimated_input_tokens=100,
                estimated_output_tokens=10,
                effective_output_cap_tokens=50,
                reserved_total_tokens=150,
                dispatch_context=CapacityAdmissionDispatchContextSummary(
                    source_ref=_document_ref().value,
                    source_unit_ref="source-unit:project-1:abc:1",
                ),
            ),
        ),
        projection_leases=(
            CapacityAdmissionProjectionLeaseSummary(
                work_item_id="work-1",
                lane=lane,
                previous_status="ready",
                status="leased",
                event_id=projection_event_id,
            ),
        ),
        started_attempts=(
            CapacityAdmissionStartedAttemptSummary(
                work_item_id="work-1",
                attempt_id="attempt-1",
                attempt_number=1,
            ),
        ),
        frontend_event_summary=CapacityAdmissionFrontendEventSummary(
            event_kind="capacity_admission_pass_completed",
            workflow_run_id=_workflow_run_id(),
            phase=CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.phase,
            operation_key=CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.operation_key,
            work_kind=CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.work_kind,
            lane=lane,
            admitted_count=1,
            started_attempt_count=1,
            work_item_ids=("work-1",),
            attempt_ids=("attempt-1",),
            projection_event_ids=(projection_event_id,),
            occurred_at=_now(),
        ),
        log_event=CapacityWindowAdmissionLogEvent.PASS_COMPLETED,
    )


def _draft_claim_compaction_admission_result() -> CapacityWindowAdmissionPassResult:
    lane = CapacityAdmissionLaneSummary(
        work_kind=DRAFT_CLAIM_COMPACTION_ADMISSION_PHASE_PROFILE.work_kind,
        provider="groq",
        account_ref="groq-account-1",
        model_ref="openai/gpt-oss-120b",
    )
    projection_event_id = UUID("00000000-0000-0000-0000-000000000502")
    dispatch_context = CapacityAdmissionDispatchContextSummary(
        group_ref="group-1",
        batch_ref="batch-1",
        round_index=0,
        expected_output_kind="compacted_claims",
        input_claim_refs=("claim-a", "claim-b"),
        input_node_refs=("raw:workflow-1:group-1:claim-a",),
    )
    return CapacityWindowAdmissionPassResult(
        workflow_run_id=_workflow_run_id(),
        phase=DRAFT_CLAIM_COMPACTION_ADMISSION_PHASE_PROFILE.phase,
        operation_key=DRAFT_CLAIM_COMPACTION_ADMISSION_PHASE_PROFILE.operation_key,
        work_kind=DRAFT_CLAIM_COMPACTION_ADMISSION_PHASE_PROFILE.work_kind,
        lane=lane,
        admitted_items=(
            CapacityAdmissionAdmittedItemSummary(
                work_item_id="work-1",
                lane=lane,
                selection_kind="fresh",
                estimated_input_tokens=100,
                estimated_output_tokens=10,
                effective_output_cap_tokens=50,
                reserved_total_tokens=150,
                dispatch_context=dispatch_context,
            ),
        ),
        projection_leases=(
            CapacityAdmissionProjectionLeaseSummary(
                work_item_id="work-1",
                lane=lane,
                previous_status="ready",
                status="leased",
                event_id=projection_event_id,
            ),
        ),
        started_attempts=(
            CapacityAdmissionStartedAttemptSummary(
                work_item_id="work-1",
                attempt_id="attempt-1",
                attempt_number=1,
            ),
        ),
        frontend_event_summary=CapacityAdmissionFrontendEventSummary(
            event_kind="capacity_admission_pass_completed",
            workflow_run_id=_workflow_run_id(),
            phase=DRAFT_CLAIM_COMPACTION_ADMISSION_PHASE_PROFILE.phase,
            operation_key=DRAFT_CLAIM_COMPACTION_ADMISSION_PHASE_PROFILE.operation_key,
            work_kind=DRAFT_CLAIM_COMPACTION_ADMISSION_PHASE_PROFILE.work_kind,
            lane=lane,
            admitted_count=1,
            started_attempt_count=1,
            work_item_ids=("work-1",),
            attempt_ids=("attempt-1",),
            projection_event_ids=(projection_event_id,),
            dispatch_contexts=(dispatch_context,),
            occurred_at=_now(),
        ),
        log_event=CapacityWindowAdmissionLogEvent.PASS_COMPLETED,
    )


@pytest.mark.asyncio
async def test_dispatch_prepare_claim_builder_uses_capacity_admission_when_provided() -> (
    None
):
    admission_pass = FakeCapacityWindowAdmissionPass(
        result=_claim_builder_admission_result()
    )
    workflow_unit_of_work = FakeWorkflowRuntimeUnitOfWork()

    result = await DispatchKnowledgeExtractionWorkflowCommandHandler().execute(
        DispatchKnowledgeExtractionWorkflowCommand(
            workflow_command=_workflow_command(
                KnowledgeExtractionCanonicalCommandType.PREPARE_CLAIM_BUILDER_DISPATCH_BATCH,
            )
        ),
        source_unit_repository=FakeSourceManagementRepository(),
        knowledge_unit_of_work=FakeWorkItemSchedulingRepository(),
        workflow_unit_of_work=workflow_unit_of_work,
        capacity_window_admission_pass=admission_pass,
    )

    assert result.dispatched is True
    assert result.blocked_reason is None
    assert len(admission_pass.calls) == 1
    assert (
        workflow_unit_of_work.command_log.pending_commands[0].command_type
        == KnowledgeExtractionCanonicalCommandType.EXECUTE_CLAIM_BUILDER_SECTION.value
    )


@pytest.mark.asyncio
async def test_dispatch_prepare_draft_claim_compaction_uses_capacity_admission_when_provided() -> (
    None
):
    admission_pass = FakeCapacityWindowAdmissionPass(
        result=_draft_claim_compaction_admission_result()
    )
    workflow_unit_of_work = FakeWorkflowRuntimeUnitOfWork()

    result = await DispatchKnowledgeExtractionWorkflowCommandHandler().execute(
        DispatchKnowledgeExtractionWorkflowCommand(
            workflow_command=_workflow_command(
                KnowledgeExtractionCanonicalCommandType.PREPARE_DRAFT_CLAIM_COMPACTION_DISPATCH_BATCH,
                payload=_draft_claim_compaction_dispatch_payload(),
            )
        ),
        source_unit_repository=FakeSourceManagementRepository(),
        knowledge_unit_of_work=FakeWorkItemSchedulingRepository(),
        workflow_unit_of_work=workflow_unit_of_work,
        capacity_window_admission_pass=admission_pass,
    )

    assert result.dispatched is True
    assert result.blocked_reason is None
    assert len(admission_pass.calls) == 1
    assert (
        workflow_unit_of_work.command_log.pending_commands[0].command_type
        == KnowledgeExtractionCanonicalCommandType.EXECUTE_DRAFT_CLAIM_COMPACTION.value
    )
