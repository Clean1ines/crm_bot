from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.knowledge_workbench.application.sagas.handle_cluster_draft_claims_command import (
    DraftClaimCompactionPlanConflictError,
    HandleClusterDraftClaimsCommand,
    HandleClusterDraftClaimsCommandHandler,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalCommandType,
    KnowledgeExtractionCanonicalEventType,
)
from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_models import (
    DraftClaimCompactionBatchCandidate,
    DraftClaimCompactionEdgeCandidate,
    DraftClaimCompactionGroupCandidate,
    DraftClaimForCompaction,
)
from src.contexts.knowledge_workbench.extraction.application.ports.draft_claim_compaction_plan_repository_port import (
    DraftClaimCompactionPlanPersistenceResult,
)
from src.contexts.knowledge_workbench.extraction.application.ports.draft_claim_compaction_reduction_state_repository_port import (
    DraftClaimCompactionReductionStatePersistenceResult,
)
from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_reduction_models import (
    DraftClaimCompactionNode,
    DraftClaimCompactionPlannerState,
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


EMBEDDING_MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"


def _now() -> datetime:
    return datetime(2026, 6, 14, 12, 0, tzinfo=timezone.utc)


def _workflow_run_id() -> str:
    return "workflow-1"


def _command(
    command_type: KnowledgeExtractionCanonicalCommandType,
    *,
    status: WorkflowCommandStatus = WorkflowCommandStatus.PENDING,
) -> WorkflowCommand:
    return WorkflowCommand(
        command_id=WorkflowCommandId(f"workflow-command:{command_type.value}"),
        command_type=command_type.value,
        workflow_run_id=_workflow_run_id(),
        idempotency_key=WorkflowIdempotencyKey(f"{command_type.value}:workflow-1"),
        payload={
            "workflow_run_id": _workflow_run_id(),
            "embedding_model_id": EMBEDDING_MODEL_ID,
        },
        status=status,
        run_after=_now(),
        created_at=_now(),
        updated_at=_now(),
    )


def _claim(ref: str) -> DraftClaimForCompaction:
    return DraftClaimForCompaction(
        observation_ref=ref,
        embedding_ref=f"embedding:{ref}",
        workflow_run_id=_workflow_run_id(),
        source_document_ref="document-1",
        source_unit_ref=f"unit:{ref}",
        claim="Product supports refunds",
        possible_questions=("Does product support refunds?",),
        exclusion_scope=(),
        granularity="atomic",
        embedding_text="Product supports refunds",
        embedding_model_id=EMBEDDING_MODEL_ID,
        dimensions=2,
        vector=(1.0, 0.0),
    )


@dataclass(slots=True)
class FakeCompactionRepository:
    claims: tuple[DraftClaimForCompaction, ...]
    persistence_result: DraftClaimCompactionPlanPersistenceResult | None = None
    persisted_edges: tuple[DraftClaimCompactionEdgeCandidate, ...] = ()
    persisted_groups: tuple[DraftClaimCompactionGroupCandidate, ...] = ()
    persisted_batches: tuple[DraftClaimCompactionBatchCandidate, ...] = ()

    async def list_claims_for_compaction(
        self,
        *,
        workflow_run_id: str,
        embedding_model_id: str,
    ) -> tuple[DraftClaimForCompaction, ...]:
        assert workflow_run_id == _workflow_run_id()
        assert embedding_model_id == EMBEDDING_MODEL_ID
        return self.claims

    async def persist_compaction_plan(
        self,
        *,
        edges: tuple[DraftClaimCompactionEdgeCandidate, ...],
        groups: tuple[DraftClaimCompactionGroupCandidate, ...],
        batches: tuple[DraftClaimCompactionBatchCandidate, ...],
        created_at: datetime,
    ) -> DraftClaimCompactionPlanPersistenceResult:
        assert created_at == _now()
        self.persisted_edges = edges
        self.persisted_groups = groups
        self.persisted_batches = batches
        return self.persistence_result or DraftClaimCompactionPlanPersistenceResult(
            requested_edge_count=len(edges),
            inserted_edge_count=len(edges),
            requested_group_count=len(groups),
            inserted_group_count=len(groups),
            requested_member_count=sum(group.member_count for group in groups),
            inserted_member_count=sum(group.member_count for group in groups),
            requested_batch_count=len(batches),
            inserted_batch_count=len(batches),
            already_exists_count=0,
        )


@dataclass(slots=True)
class FakeReductionStateRepository:
    seeded_by_group: dict[str, tuple[DraftClaimCompactionNode, ...]] = field(
        default_factory=dict
    )

    async def load_planner_state(
        self,
        *,
        workflow_run_id: str,
        group_ref: str,
    ) -> DraftClaimCompactionPlannerState | None:
        del workflow_run_id, group_ref
        return None

    async def seed_initial_planner_state(
        self,
        *,
        workflow_run_id: str,
        group_ref: str,
        raw_nodes: tuple[DraftClaimCompactionNode, ...],
        created_at: datetime,
    ) -> DraftClaimCompactionReductionStatePersistenceResult:
        assert workflow_run_id == _workflow_run_id()
        assert created_at == _now()
        self.seeded_by_group[group_ref] = raw_nodes
        requested_source_count = sum(len(node.sources) for node in raw_nodes)
        return DraftClaimCompactionReductionStatePersistenceResult(
            requested_node_count=len(raw_nodes),
            inserted_node_count=len(raw_nodes),
            requested_source_count=requested_source_count,
            inserted_source_count=requested_source_count,
            requested_comparison_count=0,
            inserted_comparison_count=0,
            already_exists_count=0,
        )


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
    pending_commands: list[WorkflowCommand] = field(default_factory=list)

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
        return _command(KnowledgeExtractionCanonicalCommandType.CLUSTER_DRAFT_CLAIMS)

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
async def test_rejects_wrong_command_type() -> None:
    with pytest.raises(ValueError, match="ClusterDraftClaims"):
        await HandleClusterDraftClaimsCommandHandler().execute(
            HandleClusterDraftClaimsCommand(
                workflow_command=_command(
                    KnowledgeExtractionCanonicalCommandType.GENERATE_DRAFT_CLAIM_EMBEDDINGS
                )
            ),
            compaction_plan_repository=FakeCompactionRepository(()),
            work_item_scheduling_repository=FakeWorkItemSchedulingRepository(),
            workflow_unit_of_work=FakeWorkflowUnitOfWork(),
            compaction_reduction_state_repository=FakeReductionStateRepository(),
        )


@pytest.mark.asyncio
async def test_rejects_non_pending_command() -> None:
    with pytest.raises(ValueError, match="PENDING"):
        await HandleClusterDraftClaimsCommandHandler().execute(
            HandleClusterDraftClaimsCommand(
                workflow_command=_command(
                    KnowledgeExtractionCanonicalCommandType.CLUSTER_DRAFT_CLAIMS,
                    status=WorkflowCommandStatus.COMPLETED,
                )
            ),
            compaction_plan_repository=FakeCompactionRepository(()),
            work_item_scheduling_repository=FakeWorkItemSchedulingRepository(),
            workflow_unit_of_work=FakeWorkflowUnitOfWork(),
            compaction_reduction_state_repository=FakeReductionStateRepository(),
        )


@pytest.mark.asyncio
async def test_builds_persists_schedules_events_progress_and_completion() -> None:
    repository = FakeCompactionRepository((_claim("claim-a"), _claim("claim-b")))
    scheduling = FakeWorkItemSchedulingRepository()
    workflow_uow = FakeWorkflowUnitOfWork()
    reduction_state = FakeReductionStateRepository()

    result = await HandleClusterDraftClaimsCommandHandler().execute(
        HandleClusterDraftClaimsCommand(
            workflow_command=_command(
                KnowledgeExtractionCanonicalCommandType.CLUSTER_DRAFT_CLAIMS
            )
        ),
        compaction_plan_repository=repository,
        work_item_scheduling_repository=scheduling,
        workflow_unit_of_work=workflow_uow,
        compaction_reduction_state_repository=reduction_state,
    )

    assert result.group_count >= 1
    assert result.batch_count >= 1
    assert len(repository.persisted_batches) == len(scheduling.saved_payloads)
    assert set(reduction_state.seeded_by_group) == {
        group.group_ref for group in repository.persisted_groups
    }
    assert sum(len(nodes) for nodes in reduction_state.seeded_by_group.values()) == sum(
        group.member_count for group in repository.persisted_groups
    )
    for group_ref, nodes in reduction_state.seeded_by_group.items():
        for node in nodes:
            assert node.node_ref.startswith(f"raw:{_workflow_run_id()}:{group_ref}:")
            assert node.node_kind.value == "raw"
            assert node.active is True
            assert len(node.source_claim_refs) == 1
    assert set(reduction_state.seeded_by_group) == {
        group.group_ref for group in repository.persisted_groups
    }
    assert sum(len(nodes) for nodes in reduction_state.seeded_by_group.values()) == sum(
        group.member_count for group in repository.persisted_groups
    )
    for group_ref, nodes in reduction_state.seeded_by_group.items():
        for node in nodes:
            assert node.node_ref.startswith(f"raw:{_workflow_run_id()}:{group_ref}:")
            assert node.node_kind.value == "raw"
            assert node.active is True
            assert len(node.source_claim_refs) == 1
    assert workflow_uow.outbox.events[0].event_type == (
        KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_CLUSTERS_BUILT.value
    )
    assert workflow_uow.progress_snapshots.snapshot is not None
    assert (
        workflow_uow.progress_snapshots.snapshot.current_phase
        == "DRAFT_CLAIM_CLUSTERING"
    )
    assert workflow_uow.progress_snapshots.snapshot.domain_counters[
        "draft_claim_compaction_batch_count"
    ] == len(repository.persisted_batches)
    assert len(workflow_uow.command_log.pending_commands) == 1
    prepare_command = workflow_uow.command_log.pending_commands[0]
    assert prepare_command.command_type == (
        KnowledgeExtractionCanonicalCommandType.PREPARE_DRAFT_CLAIM_COMPACTION_DISPATCH_BATCH.value
    )
    assert prepare_command.payload["work_kind"] == (
        "knowledge_workbench.draft_claim_compaction"
    )
    dispatch_preparation = prepare_command.payload["llm_dispatch_preparation"]
    assert isinstance(dispatch_preparation, dict)
    assert dispatch_preparation["active_model_ref"] == "openai/gpt-oss-120b"
    assert dispatch_preparation["requested_items"] == len(scheduling.saved_payloads)
    assert "account_capacities" not in dispatch_preparation
    for payload in scheduling.saved_payloads:
        provider_messages = payload["provider_messages"]
        assert isinstance(provider_messages, list)
        assert [message["role"] for message in provider_messages] == [
            "system",
            "user",
        ]
    assert workflow_uow.command_log.completed == [
        WorkflowCommandId(
            "workflow-command:"
            f"{KnowledgeExtractionCanonicalCommandType.CLUSTER_DRAFT_CLAIMS.value}"
        )
    ]
    assert workflow_uow.timeline.entries[0].message == (
        "Hybrid draft claim compaction plan built"
    )


@pytest.mark.asyncio
async def test_changed_existing_plan_raises_controlled_conflict_before_outbox() -> None:
    repository = FakeCompactionRepository(
        (_claim("claim-a"), _claim("claim-b")),
        persistence_result=DraftClaimCompactionPlanPersistenceResult(
            requested_edge_count=1,
            inserted_edge_count=1,
            requested_group_count=1,
            inserted_group_count=0,
            requested_member_count=2,
            inserted_member_count=0,
            requested_batch_count=1,
            inserted_batch_count=0,
            already_exists_count=4,
        ),
    )
    workflow_uow = FakeWorkflowUnitOfWork()

    with pytest.raises(
        DraftClaimCompactionPlanConflictError,
        match="explicit versioned rebuild path",
    ):
        await HandleClusterDraftClaimsCommandHandler().execute(
            HandleClusterDraftClaimsCommand(
                workflow_command=_command(
                    KnowledgeExtractionCanonicalCommandType.CLUSTER_DRAFT_CLAIMS
                )
            ),
            compaction_plan_repository=repository,
            work_item_scheduling_repository=FakeWorkItemSchedulingRepository(),
            workflow_unit_of_work=workflow_uow,
            compaction_reduction_state_repository=FakeReductionStateRepository(),
        )

    assert workflow_uow.outbox.events == []
