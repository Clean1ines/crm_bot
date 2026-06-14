from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
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
    DraftClaimCompactionNextWorkItem,
    DraftClaimCompactionNextWorkItemType,
    DraftClaimCompactionPlannerDecision,
    DraftClaimCompactionPlannerState,
)
from src.contexts.knowledge_workbench.extraction.application.ports.draft_claim_compaction_reduction_state_repository_port import (
    DraftClaimCompactionApplyPersistenceResult,
    DraftClaimCompactionReductionStatePersistenceResult,
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
                "granularity": "atomic",
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
        raise AssertionError("seed must not be called")

    async def apply_compacted_claims_result(
        self,
        *,
        workflow_run_id: str,
        group_ref: str,
        batch_ref: str,
        work_item_id: str,
        round_index: int,
        compacted_claims,
        created_at: datetime,
    ) -> DraftClaimCompactionApplyPersistenceResult:
        assert workflow_run_id == _workflow_run_id()
        assert group_ref == "group-1"
        assert batch_ref == "batch-1"
        assert work_item_id == "work-item-1"
        assert round_index == 0
        assert created_at == _now()
        assert compacted_claims[0].source_claim_refs == ("claim-a", "claim-b")
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
class FakeWorkItemSchedulingRepository:
    saved_payloads: list[object] = field(default_factory=list)

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
        del item, idempotency_key, payload_hash
        self.saved_payloads.append(payload)


@dataclass(slots=True)
class FakeCommandLog:
    completed: list[WorkflowCommandId] = field(default_factory=list)

    async def append_pending_command(self, command: WorkflowCommand) -> WorkflowCommand:
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
    assert scheduling.saved_payloads == []


@pytest.mark.asyncio
async def test_schedules_next_work_item_for_reduced_rewrite_decision() -> None:
    workflow_uow = FakeWorkflowUnitOfWork()
    scheduling = FakeWorkItemSchedulingRepository()
    repository = FakeReductionStateRepository(
        _decision(
            DraftClaimCompactionNextWorkItemType.REDUCED_REWRITE,
            node_refs=("compacted-a", "compacted-b"),
        )
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
        work_item_scheduling_repository=scheduling,
    )

    assert scheduling.saved_payloads == []
    event = workflow_uow.outbox.events[-1]
    assert (
        event.event_type
        == KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_WAITING_USER_MODEL_CHOICE.value
    )
    assert event.payload["degraded_candidate_model_id"] == "llama-3.3-70b-versatile"


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
            work_item_scheduling_repository=FakeWorkItemSchedulingRepository(),
        )


def _decision(
    work_type: DraftClaimCompactionNextWorkItemType,
    *,
    node_refs: tuple[str, ...] = (),
) -> DraftClaimCompactionPlannerDecision:
    return DraftClaimCompactionPlannerDecision(
        next_work_item=DraftClaimCompactionNextWorkItem(
            work_type=work_type,
            node_refs=node_refs,
            degraded_model_id="llama-3.3-70b-versatile"
            if work_type
            is DraftClaimCompactionNextWorkItemType.WAIT_FOR_USER_MODEL_CHOICE
            else None,
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
