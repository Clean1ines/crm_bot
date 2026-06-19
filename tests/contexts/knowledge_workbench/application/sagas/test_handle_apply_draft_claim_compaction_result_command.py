from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from src.contexts.execution_runtime.application.use_cases.ensure_work_items_scheduled import (
    work_item_schedule_payload_hash,
)
from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.knowledge_workbench.application.sagas.handle_apply_draft_claim_compaction_result_command import (
    HandleApplyDraftClaimCompactionResultCommand,
    HandleApplyDraftClaimCompactionResultCommandHandler,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalCommandType,
    KnowledgeExtractionCanonicalEventType,
)
from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_apply_result import (
    DraftClaimCompactionApplyResultCommand,
    DraftClaimCompactionApplyResultOutcome,
)
from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_reduction_models import (
    DraftClaimCompactionNode,
    DraftClaimCompactionNodeKind,
    DraftClaimCompactionNextWorkItem,
    DraftClaimCompactionNextWorkItemType,
    DraftClaimCompactionPlannerDecision,
    DraftClaimCompactionPlannerState,
)
from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_prompt_contract import (
    DraftClaimCompactionPromptClaim,
    DraftClaimCompactionPromptPayload,
)
from src.contexts.knowledge_workbench.extraction.application.ports.draft_claim_compaction_reduction_state_repository_port import (
    DraftClaimCompactionApplyPersistenceResult,
    DraftClaimCompactionReductionStatePersistenceResult,
)
from src.contexts.knowledge_workbench.extraction.application.ports.draft_claim_observation_read_repository_port import (
    DraftClaimObservationReadModel,
)
from src.contexts.knowledge_workbench.extraction.application.policies.draft_claim_compaction_provider_messages import (
    build_draft_claim_compaction_provider_messages,
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
    return datetime(2026, 6, 14, 12, 0, tzinfo=timezone.utc)


def _workflow_run_id() -> str:
    return "workflow-1"


def _command_causation_scope(command: WorkflowCommand) -> str:
    return hashlib.sha256(
        command.command_id.value.encode("utf-8"),
    ).hexdigest()[:12]


def _command(
    *,
    command_type: KnowledgeExtractionCanonicalCommandType = (
        KnowledgeExtractionCanonicalCommandType.APPLY_DRAFT_CLAIM_COMPACTION_RESULT
    ),
    status: WorkflowCommandStatus = WorkflowCommandStatus.PENDING,
    output_kind: str = "compacted_claims",
) -> WorkflowCommand:
    payload: dict[str, object] = {
        "workflow_run_id": _workflow_run_id(),
        "group_ref": "group-1",
        "batch_ref": "batch-1",
        "work_item_id": "work-item-1",
        "round_index": 0,
        "output_kind": output_kind,
        "left_node_ref": "raw:workflow-1:group-1:claim-a",
        "right_node_ref": "raw:workflow-1:group-1:claim-b",
        "compacted_claims": [
            {
                "key": "refund_support",
                "claim": "Product supports refunds.",
                "claim_kind": "capability",
                "source_claim_refs": ["claim-a", "claim-b"],
                "triples": [_triple_json()],
                "merge_decision": "merged",
            }
        ],
        "reduced_rewrite": None,
    }
    if output_kind == "reduced_rewrite":
        payload["right_node_ref"] = "compacted-b"
        payload["left_node_ref"] = "compacted-a"
        payload["compacted_claims"] = []
        payload["reduced_rewrite"] = {
            "key": "refund_support",
            "claim": "Product supports refunds.",
            "triples": [_triple_json()],
        }
    return WorkflowCommand(
        command_id=WorkflowCommandId(f"workflow-command:{command_type.value}"),
        command_type=command_type.value,
        workflow_run_id=_workflow_run_id(),
        idempotency_key=WorkflowIdempotencyKey(f"{command_type.value}:workflow-1"),
        payload=payload,
        status=status,
        run_after=_now(),
        created_at=_now(),
        updated_at=_now(),
    )


@dataclass(slots=True)
class FakeApplyResultUseCase:
    next_decision: DraftClaimCompactionPlannerDecision
    commands: list[DraftClaimCompactionApplyResultCommand] = field(default_factory=list)

    async def execute(
        self,
        command: DraftClaimCompactionApplyResultCommand,
    ) -> DraftClaimCompactionApplyResultOutcome:
        self.commands.append(command)
        return DraftClaimCompactionApplyResultOutcome(
            created_node_refs=("compacted-node",),
            superseded_node_refs=("raw-a", "raw-b"),
            comparison_refs=("comparison-a-b",),
            next_decision=self.next_decision,
        )


@dataclass(slots=True)
class FakeReductionStateRepository:
    next_decision: DraftClaimCompactionPlannerDecision
    planner_nodes: tuple[DraftClaimCompactionNode, ...] = ()
    applied_compacted: int = 0
    applied_reduced: int = 0

    async def load_planner_state(
        self,
        *,
        workflow_run_id: str,
        group_ref: str,
    ) -> DraftClaimCompactionPlannerState | None:
        assert workflow_run_id == _workflow_run_id()
        assert group_ref == "group-1"
        return DraftClaimCompactionPlannerState(
            cluster_ref="group-1",
            nodes=self.planner_nodes,
        )

    async def seed_initial_planner_state(
        self,
        *,
        workflow_run_id: str,
        group_ref: str,
        raw_nodes,
        created_at: datetime,
    ) -> DraftClaimCompactionReductionStatePersistenceResult:
        del workflow_run_id, group_ref, raw_nodes, created_at
        raise AssertionError("seed must not be called")

    async def apply_compacted_claims_result(
        self,
        *,
        workflow_run_id: str,
        group_ref: str,
        batch_ref: str,
        work_item_id: str,
        round_index: int,
        compared_node_refs,
        compacted_claims,
        created_at: datetime,
    ) -> DraftClaimCompactionApplyPersistenceResult:
        assert workflow_run_id == _workflow_run_id()
        assert group_ref == "group-1"
        assert batch_ref == "batch-1"
        assert work_item_id == "work-item-1"
        assert round_index == 0
        assert tuple(compared_node_refs) == (
            "raw:workflow-1:group-1:claim-a",
            "raw:workflow-1:group-1:claim-b",
        )
        assert created_at == _now()
        assert compacted_claims[0].source_claim_refs == ("claim-a", "claim-b")
        assert compacted_claims[0].possible_questions == ("Q claim-a", "Q claim-b")
        assert (
            compacted_claims[0].evidence_block == "Evidence claim-a\n\nEvidence claim-b"
        )
        self.applied_compacted += 1
        return _apply_persistence()

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
        assert workflow_run_id == _workflow_run_id()
        assert group_ref == "group-1"
        assert batch_ref == "batch-1"
        assert work_item_id == "work-item-1"
        assert round_index == 0
        assert source_node_refs == ("compacted-a", "compacted-b")
        assert rewrite.key == "refund_support"
        assert created_at == _now()
        self.applied_reduced += 1
        return _apply_persistence()


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


@dataclass(slots=True)
class FakeWorkItemSchedulingRepository:
    saved_payloads: list[object] = field(default_factory=list)
    existing_payload_hashes: dict[str, str] = field(default_factory=dict)
    existing_work_kinds: dict[str, WorkKind] = field(default_factory=dict)

    async def get_work_item(self, work_item_id: str) -> WorkItem | None:
        work_kind = self.existing_work_kinds.get(work_item_id)
        if work_kind is None:
            return None
        return WorkItem(
            work_item_id=work_item_id,
            work_kind=work_kind,
        )

    async def get_schedule_payload_hash(self, work_item_id: str) -> str | None:
        return self.existing_payload_hashes.get(work_item_id)

    async def save_scheduled_work_item(
        self,
        *,
        item: WorkItem,
        idempotency_key: str,
        payload_hash: str,
        payload: object,
    ) -> None:
        del idempotency_key
        self.saved_payloads.append(payload)
        self.existing_payload_hashes[item.work_item_id] = payload_hash
        self.existing_work_kinds[item.work_item_id] = item.work_kind


@dataclass(slots=True)
class FakeCommandLog:
    completed: list[WorkflowCommandId] = field(default_factory=list)
    pending_commands: list[WorkflowCommand] = field(default_factory=list)
    pending_by_idempotency_key: dict[str, WorkflowCommand] = field(default_factory=dict)

    async def append_pending_command(self, command: WorkflowCommand) -> WorkflowCommand:
        existing = self.pending_by_idempotency_key.get(command.idempotency_key.value)
        if existing is not None:
            if existing.command_type != command.command_type:
                raise ValueError("idempotency_key conflict has different command_type")
            if existing.workflow_run_id != command.workflow_run_id:
                raise ValueError(
                    "idempotency_key conflict has different workflow_run_id"
                )
            if dict(existing.payload) != dict(command.payload):
                raise ValueError("idempotency_key conflict has different payload")
            return existing

        self.pending_commands.append(command)
        self.pending_by_idempotency_key[command.idempotency_key.value] = command
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
class FakeEventCursors:
    async def get_cursor(
        self, consumer_ref: WorkflowConsumerRef
    ) -> WorkflowEventCursor | None:
        del consumer_ref
        return None

    async def save_cursor(self, cursor: WorkflowEventCursor) -> WorkflowEventCursor:
        return cursor


@dataclass(slots=True)
class FakeProgressSnapshots:
    snapshot: WorkflowProgressSnapshot | None = None

    async def get_snapshot(
        self, workflow_run_id: str
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
        self, workflow_run_id: str
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


@pytest.mark.asyncio
async def test_applies_result_events_progress_timeline_and_completes_command() -> None:
    workflow_uow = FakeWorkflowUnitOfWork()
    scheduling = FakeWorkItemSchedulingRepository()
    repository = FakeReductionStateRepository(
        _decision(DraftClaimCompactionNextWorkItemType.DONE)
    )

    apply_use_case = FakeApplyResultUseCase(
        _decision(DraftClaimCompactionNextWorkItemType.DONE)
    )

    result = await HandleApplyDraftClaimCompactionResultCommandHandler(
        apply_result_use_case=apply_use_case,
    ).execute(
        HandleApplyDraftClaimCompactionResultCommand(workflow_command=_command()),
        workflow_unit_of_work=workflow_uow,
        compaction_reduction_state_repository=repository,
        draft_claim_observation_read_repository=FakeDraftClaimObservationReadRepository(),
        work_item_scheduling_repository=scheduling,
    )

    event_types = [event.event_type for event in workflow_uow.outbox.events]
    assert len(apply_use_case.commands) == 1
    assert apply_use_case.commands[0].output_kind.value == "compacted_claims"
    assert event_types == [
        KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_RESULT_APPLIED.value,
        KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_CLUSTER_DONE.value,
    ]
    assert len(workflow_uow.timeline.entries) == 2
    assert workflow_uow.progress_snapshots.snapshot is not None
    assert workflow_uow.command_log.completed == [_command().command_id]
    assert result.next_work_type == "done"
    assert result.appended_next_command_count == 1
    assert result.next_command_type == (
        KnowledgeExtractionCanonicalCommandType.RECONCILE_DRAFT_CLAIM_COMPACTION_PROGRESS.value
    )
    assert scheduling.saved_payloads == []
    assert [
        command.command_type for command in workflow_uow.command_log.pending_commands
    ] == [
        KnowledgeExtractionCanonicalCommandType.RECONCILE_DRAFT_CLAIM_COMPACTION_PROGRESS.value
    ]
    assert workflow_uow.command_log.pending_commands[0].payload == {
        "workflow_run_id": _workflow_run_id(),
        "group_ref": "group-1",
        "caused_by_command_id": _command().command_id.value,
    }


@pytest.mark.asyncio
async def test_constructed_apply_use_case_receives_raw_claim_read_repository() -> None:
    workflow_uow = FakeWorkflowUnitOfWork()
    scheduling = FakeWorkItemSchedulingRepository()
    repository = FakeReductionStateRepository(
        _decision(DraftClaimCompactionNextWorkItemType.DONE)
    )
    read_repository = FakeDraftClaimObservationReadRepository()

    await HandleApplyDraftClaimCompactionResultCommandHandler().execute(
        HandleApplyDraftClaimCompactionResultCommand(workflow_command=_command()),
        workflow_unit_of_work=workflow_uow,
        compaction_reduction_state_repository=repository,
        draft_claim_observation_read_repository=read_repository,
        work_item_scheduling_repository=scheduling,
    )

    assert read_repository.requested_refs == [("claim-a", "claim-b")]
    assert repository.applied_compacted == 1


@pytest.mark.asyncio
async def test_schedules_next_work_item_for_reduced_rewrite_decision() -> None:
    workflow_uow = FakeWorkflowUnitOfWork()
    scheduling = FakeWorkItemSchedulingRepository()
    repository = FakeReductionStateRepository(
        _decision(
            DraftClaimCompactionNextWorkItemType.REDUCED_REWRITE,
            node_refs=("compacted-a", "compacted-b"),
        ),
        planner_nodes=(_compacted_node("compacted-a"), _compacted_node("compacted-b")),
    )

    apply_use_case = FakeApplyResultUseCase(
        _decision(
            DraftClaimCompactionNextWorkItemType.REDUCED_REWRITE,
            node_refs=("compacted-a", "compacted-b"),
        )
    )

    await HandleApplyDraftClaimCompactionResultCommandHandler(
        apply_result_use_case=apply_use_case,
    ).execute(
        HandleApplyDraftClaimCompactionResultCommand(workflow_command=_command()),
        workflow_unit_of_work=workflow_uow,
        compaction_reduction_state_repository=repository,
        draft_claim_observation_read_repository=FakeDraftClaimObservationReadRepository(),
        work_item_scheduling_repository=scheduling,
    )

    assert len(scheduling.saved_payloads) == 1
    payload = scheduling.saved_payloads[0]
    assert isinstance(payload, dict)
    assert payload["prompt_variant"] == "reduced_rewrite"
    assert payload["node_refs"] == ["compacted-a", "compacted-b"]
    assert "source_claim_refs" not in payload
    assert (
        KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_NEXT_WORK_SCHEDULED.value
        in [event.event_type for event in workflow_uow.outbox.events]
    )
    assert [
        command.command_type for command in workflow_uow.command_log.pending_commands
    ] == [
        KnowledgeExtractionCanonicalCommandType.PREPARE_DRAFT_CLAIM_COMPACTION_DISPATCH_BATCH.value
    ]
    prepare_payload = workflow_uow.command_log.pending_commands[0].payload
    assert prepare_payload["scheduled_work_item_count"] == 1
    assert prepare_payload["llm_dispatch_preparation"]["requested_items"] == 1
    assert (
        prepare_payload["llm_dispatch_preparation"]["active_model_ref"]
        == "openai/gpt-oss-120b"
    )
    assert (
        prepare_payload["llm_dispatch_preparation"]["worker_ref"]
        == "knowledge-workbench-draft-claim-compaction-dispatch"
    )


@pytest.mark.asyncio
async def test_waiting_user_model_choice_appends_event_without_scheduling() -> None:
    workflow_uow = FakeWorkflowUnitOfWork()
    scheduling = FakeWorkItemSchedulingRepository()
    repository = FakeReductionStateRepository(
        _decision(
            DraftClaimCompactionNextWorkItemType.WAIT_FOR_USER_MODEL_CHOICE,
            node_refs=("compacted-a", "compacted-b"),
        )
    )

    apply_use_case = FakeApplyResultUseCase(
        _decision(
            DraftClaimCompactionNextWorkItemType.WAIT_FOR_USER_MODEL_CHOICE,
            node_refs=("compacted-a", "compacted-b"),
        )
    )

    await HandleApplyDraftClaimCompactionResultCommandHandler(
        apply_result_use_case=apply_use_case,
    ).execute(
        HandleApplyDraftClaimCompactionResultCommand(workflow_command=_command()),
        workflow_unit_of_work=workflow_uow,
        compaction_reduction_state_repository=repository,
        draft_claim_observation_read_repository=FakeDraftClaimObservationReadRepository(),
        work_item_scheduling_repository=scheduling,
    )

    assert scheduling.saved_payloads == []
    assert workflow_uow.command_log.pending_commands == []
    event = workflow_uow.outbox.events[-1]
    assert (
        event.event_type
        == KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_WAITING_USER_MODEL_CHOICE.value
    )
    assert event.payload["degraded_candidate_model_id"] == "llama-3.3-70b-versatile"
    assert event.payload["node_refs"] == ["compacted-a", "compacted-b"]
    assert event.payload["resume_work_type"] == "compacted_vs_compacted"


@pytest.mark.asyncio
async def test_rejects_wrong_command_type() -> None:
    with pytest.raises(ValueError, match="ApplyDraftClaimCompactionResult"):
        await HandleApplyDraftClaimCompactionResultCommandHandler().execute(
            HandleApplyDraftClaimCompactionResultCommand(
                workflow_command=_command(
                    command_type=KnowledgeExtractionCanonicalCommandType.CLUSTER_DRAFT_CLAIMS
                )
            ),
            workflow_unit_of_work=FakeWorkflowUnitOfWork(),
            compaction_reduction_state_repository=FakeReductionStateRepository(
                _decision(DraftClaimCompactionNextWorkItemType.DONE)
            ),
            draft_claim_observation_read_repository=FakeDraftClaimObservationReadRepository(),
            work_item_scheduling_repository=FakeWorkItemSchedulingRepository(),
        )


@pytest.mark.asyncio
async def test_rejects_non_pending_command() -> None:
    with pytest.raises(ValueError, match="PENDING"):
        await HandleApplyDraftClaimCompactionResultCommandHandler().execute(
            HandleApplyDraftClaimCompactionResultCommand(
                workflow_command=_command(status=WorkflowCommandStatus.COMPLETED)
            ),
            workflow_unit_of_work=FakeWorkflowUnitOfWork(),
            compaction_reduction_state_repository=FakeReductionStateRepository(
                _decision(DraftClaimCompactionNextWorkItemType.DONE)
            ),
            draft_claim_observation_read_repository=FakeDraftClaimObservationReadRepository(),
            work_item_scheduling_repository=FakeWorkItemSchedulingRepository(),
        )


def _decision(
    work_type: DraftClaimCompactionNextWorkItemType,
    *,
    node_refs: tuple[str, ...] = (),
    estimated_prompt_tokens: int = 1,
    estimated_completion_tokens: int | None = None,
) -> DraftClaimCompactionPlannerDecision:
    return DraftClaimCompactionPlannerDecision(
        next_work_item=DraftClaimCompactionNextWorkItem(
            work_type=work_type,
            node_refs=node_refs,
            degraded_model_id="llama-3.3-70b-versatile"
            if work_type
            is DraftClaimCompactionNextWorkItemType.WAIT_FOR_USER_MODEL_CHOICE
            else None,
            user_choice_resume_work_type=(
                DraftClaimCompactionNextWorkItemType.COMPACTED_VS_COMPACTED
                if work_type
                is DraftClaimCompactionNextWorkItemType.WAIT_FOR_USER_MODEL_CHOICE
                else None
            ),
            estimated_prompt_tokens=estimated_prompt_tokens,
            estimated_completion_tokens=4000
            if estimated_completion_tokens is None
            else estimated_completion_tokens,
        ),
        reason="test decision",
    )


def _triple_json() -> dict[str, object]:
    return {
        "subject": "Product",
        "predicate": "has_capability",
        "object": "refunds",
        "qualifiers": [],
    }


def _apply_persistence() -> DraftClaimCompactionApplyPersistenceResult:
    return DraftClaimCompactionApplyPersistenceResult(
        inserted_node_count=1,
        updated_node_count=2,
        inserted_source_count=2,
        inserted_comparison_count=1,
        superseded_node_count=2,
        already_exists_count=0,
    )


@pytest.mark.asyncio
async def test_schedules_prepare_command_after_next_compacted_work_item() -> None:
    workflow_uow = FakeWorkflowUnitOfWork()
    scheduling = FakeWorkItemSchedulingRepository()
    repository = FakeReductionStateRepository(
        _decision(
            DraftClaimCompactionNextWorkItemType.COMPACTED_VS_COMPACTED,
            node_refs=("compacted-a", "compacted-b"),
        )
    )
    apply_use_case = FakeApplyResultUseCase(
        _decision(
            DraftClaimCompactionNextWorkItemType.COMPACTED_VS_COMPACTED,
            node_refs=("compacted-a", "compacted-b"),
        )
    )

    result = await HandleApplyDraftClaimCompactionResultCommandHandler(
        apply_result_use_case=apply_use_case,
    ).execute(
        HandleApplyDraftClaimCompactionResultCommand(workflow_command=_command()),
        workflow_unit_of_work=workflow_uow,
        compaction_reduction_state_repository=repository,
        draft_claim_observation_read_repository=FakeDraftClaimObservationReadRepository(),
        work_item_scheduling_repository=scheduling,
    )

    assert len(scheduling.saved_payloads) == 1
    assert result.appended_next_command_count == 1
    assert result.next_command_type == (
        KnowledgeExtractionCanonicalCommandType.PREPARE_DRAFT_CLAIM_COMPACTION_DISPATCH_BATCH.value
    )
    assert [event.event_type for event in workflow_uow.outbox.events] == [
        KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_RESULT_APPLIED.value,
        KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_NEXT_WORK_SCHEDULED.value,
    ]

    command = workflow_uow.command_log.pending_commands[0]
    assert command.command_type == (
        KnowledgeExtractionCanonicalCommandType.PREPARE_DRAFT_CLAIM_COMPACTION_DISPATCH_BATCH.value
    )
    assert command.idempotency_key.value == (
        "draft-claim-compaction-dispatch:"
        "workflow-1:group-1:compacted_vs_compacted:compacted-a--compacted-b:"
        f"{_command_causation_scope(_command())}"
    )
    payload = command.payload
    assert payload["workflow_run_id"] == _workflow_run_id()
    assert payload["work_kind"] == "knowledge_workbench.draft_claim_compaction"
    assert payload["scheduled_work_item_count"] == 1
    dispatch_payload = payload["llm_dispatch_preparation"]
    assert dispatch_payload["requested_items"] == 1
    assert dispatch_payload["active_model_ref"] == "openai/gpt-oss-120b"
    assert (
        dispatch_payload["worker_ref"]
        == "knowledge-workbench-draft-claim-compaction-dispatch"
    )
    assert dispatch_payload["account_capacities"] == ()
    assert dispatch_payload["profile"]["estimated_prompt_tokens"] == 1
    assert dispatch_payload["profile"]["estimated_completion_tokens"] == 4000
    assert dispatch_payload["profile"]["estimated_requests"] == 1
    scheduled_payload = scheduling.saved_payloads[0]
    assert isinstance(scheduled_payload, dict)
    assert scheduled_payload["compacted_node_refs"] == [
        "compacted-a",
        "compacted-b",
    ]
    assert scheduled_payload["raw_claim_refs"] == []
    assert scheduled_payload["estimated_prompt_tokens"] == 1
    assert scheduled_payload["estimated_completion_tokens"] == 4000
    assert [message["role"] for message in scheduled_payload["provider_messages"]] == [
        "system",
        "user",
    ]
    assert scheduled_payload["estimated_requests"] == 1
    assert scheduled_payload["llm_capacity_estimate"] == {
        "estimated_input_tokens": 1,
        "reserved_output_tokens": 4000,
    }


@pytest.mark.asyncio
async def test_appends_prepare_command_when_next_work_item_already_exists() -> None:
    workflow_uow = FakeWorkflowUnitOfWork()
    work_type = DraftClaimCompactionNextWorkItemType.COMPACTED_VS_COMPACTED
    node_refs = ("compacted-a", "compacted-b")
    schedule_payload = _expected_next_work_schedule_payload(work_type, node_refs)
    work_item_id = (
        "claim-compaction:workflow-1:"
        "group-1:compacted_vs_compacted:compacted-a--compacted-b"
    )
    scheduling = FakeWorkItemSchedulingRepository(
        existing_payload_hashes={
            work_item_id: work_item_schedule_payload_hash(schedule_payload),
        },
        existing_work_kinds={
            work_item_id: WorkKind("knowledge_workbench.draft_claim_compaction"),
        },
    )
    repository = FakeReductionStateRepository(
        _decision(work_type, node_refs=node_refs),
        planner_nodes=(_compacted_node("compacted-a"), _compacted_node("compacted-b")),
    )
    apply_use_case = FakeApplyResultUseCase(_decision(work_type, node_refs=node_refs))

    result = await HandleApplyDraftClaimCompactionResultCommandHandler(
        apply_result_use_case=apply_use_case,
    ).execute(
        HandleApplyDraftClaimCompactionResultCommand(workflow_command=_command()),
        workflow_unit_of_work=workflow_uow,
        compaction_reduction_state_repository=repository,
        draft_claim_observation_read_repository=FakeDraftClaimObservationReadRepository(),
        work_item_scheduling_repository=scheduling,
    )

    assert scheduling.saved_payloads == []
    assert result.scheduled_work_item_count == 0
    assert result.already_scheduled_work_item_count == 1
    assert result.appended_next_command_count == 1
    assert workflow_uow.command_log.pending_commands[0].command_type == (
        KnowledgeExtractionCanonicalCommandType.PREPARE_DRAFT_CLAIM_COMPACTION_DISPATCH_BATCH.value
    )


def _expected_next_work_schedule_payload(
    work_type: DraftClaimCompactionNextWorkItemType,
    node_refs: tuple[str, ...],
) -> dict[str, object]:
    provider_messages = build_draft_claim_compaction_provider_messages(
        prompt_file_name="enriched_claim_compaction.txt",
        payload=DraftClaimCompactionPromptPayload(
            claims=tuple(
                DraftClaimCompactionPromptClaim(
                    claim_id=node_ref,
                    claim=f"Compacted claim {node_ref}",
                    questions=(),
                )
                for node_ref in node_refs
            ),
            prompt_variant=work_type.value,
        ).to_json_dict(),
    )
    return {
        "workflow_run_id": _workflow_run_id(),
        "group_ref": "group-1",
        "batch_ref": f"group-1:{work_type.value}:{'--'.join(node_refs)}",
        "prompt_variant": work_type.value,
        "model_id": "openai/gpt-oss-120b",
        "provider_messages": list(provider_messages),
        "node_refs": list(node_refs),
        "compacted_node_refs": list(node_refs)
        if work_type
        in {
            DraftClaimCompactionNextWorkItemType.COMPACTED_VS_COMPACTED,
            DraftClaimCompactionNextWorkItemType.REDUCED_REWRITE,
        }
        else [],
        "raw_claim_refs": list(node_refs)
        if work_type is DraftClaimCompactionNextWorkItemType.DRAFT_VS_DRAFT
        else [],
        "estimated_prompt_tokens": 1,
        "estimated_completion_tokens": 4000,
        "estimated_requests": 1,
        "llm_capacity_estimate": {
            "estimated_input_tokens": 1,
            "reserved_output_tokens": 4000,
        },
    }


def _compacted_node(node_ref: str) -> DraftClaimCompactionNode:
    return DraftClaimCompactionNode(
        node_ref=node_ref,
        node_kind=DraftClaimCompactionNodeKind.COMPACTED,
        source_claim_refs=(f"source-{node_ref}",),
        compacted_key=f"key-{node_ref}",
        compacted_claim=f"Compacted claim {node_ref}",
    )


@pytest.mark.asyncio
async def test_repeated_apply_dispatch_does_not_duplicate_next_prepare_command() -> (
    None
):
    workflow_uow = FakeWorkflowUnitOfWork()
    scheduling = FakeWorkItemSchedulingRepository()
    work_type = DraftClaimCompactionNextWorkItemType.COMPACTED_VS_COMPACTED
    node_refs = ("compacted-a", "compacted-b")
    repository = FakeReductionStateRepository(_decision(work_type, node_refs=node_refs))
    apply_use_case = FakeApplyResultUseCase(_decision(work_type, node_refs=node_refs))

    handler = HandleApplyDraftClaimCompactionResultCommandHandler(
        apply_result_use_case=apply_use_case,
    )
    command = HandleApplyDraftClaimCompactionResultCommand(
        workflow_command=_command(),
    )

    first = await handler.execute(
        command,
        workflow_unit_of_work=workflow_uow,
        compaction_reduction_state_repository=repository,
        draft_claim_observation_read_repository=FakeDraftClaimObservationReadRepository(),
        work_item_scheduling_repository=scheduling,
    )
    second = await handler.execute(
        command,
        workflow_unit_of_work=workflow_uow,
        compaction_reduction_state_repository=repository,
        draft_claim_observation_read_repository=FakeDraftClaimObservationReadRepository(),
        work_item_scheduling_repository=scheduling,
    )

    assert first.appended_next_command_count == 1
    assert second.appended_next_command_count == 1
    assert first.next_command_type == (
        KnowledgeExtractionCanonicalCommandType.PREPARE_DRAFT_CLAIM_COMPACTION_DISPATCH_BATCH.value
    )
    assert second.next_command_type == first.next_command_type
    assert len(workflow_uow.command_log.pending_commands) == 1
    assert len(scheduling.saved_payloads) == 1
    assert workflow_uow.command_log.pending_commands[0].idempotency_key.value == (
        "draft-claim-compaction-dispatch:"
        "workflow-1:group-1:compacted_vs_compacted:compacted-a--compacted-b:"
        f"{_command_causation_scope(_command())}"
    )
