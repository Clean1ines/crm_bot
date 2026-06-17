from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass

from src.contexts.execution_runtime.application.ports.work_item_scheduling_repository_port import (
    WorkItemSchedulingRepositoryPort,
)
from src.contexts.execution_runtime.application.use_cases.ensure_work_items_scheduled import (
    EnsureWorkItemsScheduled,
    EnsureWorkItemsScheduledCommand,
    WorkItemSchedulePlan,
)
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalCommandType,
    KnowledgeExtractionCanonicalEventType,
    KnowledgeExtractionCanonicalPhase,
)
from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_apply_result import (
    raw_claim_node_ref,
)
from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_models import (
    DraftClaimCompactionGroupCandidate,
    DraftClaimForCompaction,
)
from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_reduction_models import (
    DraftClaimCompactionNode,
    DraftClaimCompactionNodeKind,
    DraftClaimCompactionNodeSource,
)
from src.contexts.knowledge_workbench.extraction.application.policies.draft_claim_compaction_batch_budget_policy import (
    DraftClaimCompactionBatchBudgetPolicy,
)
from src.contexts.knowledge_workbench.extraction.application.policies.draft_claim_compaction_grouping_policy import (
    DraftClaimCompactionGroupingPolicy,
)
from src.contexts.knowledge_workbench.extraction.application.policies.draft_claim_hybrid_similarity_policy import (
    DraftClaimHybridSimilarityPolicy,
)
from src.contexts.knowledge_workbench.extraction.application.ports.draft_claim_compaction_plan_repository_port import (
    DraftClaimCompactionPlanRepositoryPort,
)
from src.contexts.knowledge_workbench.extraction.application.ports.draft_claim_compaction_reduction_state_repository_port import (
    DraftClaimCompactionReductionStateRepositoryPort,
)
from src.contexts.workflow_runtime.application.ports.workflow_runtime_unit_of_work_port import (
    WorkflowRuntimeUnitOfWorkPort,
)
from src.contexts.workflow_runtime.domain.entities.workflow_command import (
    WorkflowCommand,
    WorkflowCommandStatus,
)
from src.contexts.workflow_runtime.domain.entities.workflow_event import WorkflowEvent
from src.contexts.workflow_runtime.domain.entities.workflow_progress_snapshot import (
    WorkflowProgressSnapshot,
)
from src.contexts.workflow_runtime.domain.entities.workflow_timeline_entry import (
    WorkflowTimelineEntry,
    WorkflowTimelineSeverity,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_command_id import (
    WorkflowCommandId,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_event_id import (
    WorkflowEventId,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_idempotency_key import (
    WorkflowIdempotencyKey,
)

WORK_KIND = WorkKind("knowledge_workbench.draft_claim_compaction")
DRAFT_CLAIM_COMPACTION_ACTIVE_MODEL_REF = "openai/gpt-oss-120b"
DRAFT_CLAIM_COMPACTION_RESERVED_OUTPUT_TOKENS = 4000
DRAFT_CLAIM_COMPACTION_WORKER_REF = (
    "knowledge-workbench-draft-claim-compaction-dispatch"
)


@dataclass(frozen=True, slots=True)
class HandleClusterDraftClaimsCommand:
    workflow_command: WorkflowCommand


@dataclass(frozen=True, slots=True)
class HandleClusterDraftClaimsResult:
    workflow_run_id: str
    candidate_edge_count: int
    group_count: int
    batch_count: int
    scheduled_work_item_count: int
    already_scheduled_work_item_count: int


class HandleClusterDraftClaimsCommandHandler:
    def __init__(
        self,
        *,
        similarity_policy: DraftClaimHybridSimilarityPolicy | None = None,
        grouping_policy: DraftClaimCompactionGroupingPolicy | None = None,
        batch_budget_policy: DraftClaimCompactionBatchBudgetPolicy | None = None,
    ) -> None:
        self._similarity_policy = (
            similarity_policy or DraftClaimHybridSimilarityPolicy()
        )
        self._grouping_policy = grouping_policy or DraftClaimCompactionGroupingPolicy()
        self._batch_budget_policy = (
            batch_budget_policy or DraftClaimCompactionBatchBudgetPolicy()
        )

    async def execute(
        self,
        command: HandleClusterDraftClaimsCommand,
        *,
        compaction_plan_repository: DraftClaimCompactionPlanRepositoryPort,
        work_item_scheduling_repository: WorkItemSchedulingRepositoryPort,
        workflow_unit_of_work: WorkflowRuntimeUnitOfWorkPort,
        compaction_reduction_state_repository: (
            DraftClaimCompactionReductionStateRepositoryPort
        ),
    ) -> HandleClusterDraftClaimsResult:
        workflow_command = command.workflow_command
        if (
            workflow_command.command_type
            != KnowledgeExtractionCanonicalCommandType.CLUSTER_DRAFT_CLAIMS.value
        ):
            raise ValueError("workflow_command command_type must be ClusterDraftClaims")
        if workflow_command.status is not WorkflowCommandStatus.PENDING:
            raise ValueError("workflow_command status must be PENDING")
        workflow_run_id = _payload_text(
            workflow_command.payload,
            "workflow_run_id",
            workflow_command.workflow_run_id,
        )
        if workflow_run_id != workflow_command.workflow_run_id:
            raise ValueError("payload workflow_run_id must match workflow command")

        claims = await compaction_plan_repository.list_claims_for_compaction(
            workflow_run_id=workflow_run_id,
            embedding_model_id=self._batch_budget_policy.model_id,
        )
        edges = self._similarity_policy.build_edges(claims)
        groups = self._grouping_policy.build_groups(claims, edges)
        budget_plan = self._batch_budget_policy.build_batches(claims, groups)
        persistence = await compaction_plan_repository.persist_compaction_plan(
            edges=edges,
            groups=budget_plan.groups,
            batches=budget_plan.batches,
            created_at=workflow_command.updated_at,
        )
        claims_by_ref = {claim.observation_ref: claim for claim in claims}
        for group in budget_plan.groups:
            await compaction_reduction_state_repository.seed_initial_planner_state(
                workflow_run_id=workflow_run_id,
                group_ref=group.group_ref,
                raw_nodes=_raw_nodes_for_group(
                    workflow_run_id=workflow_run_id,
                    group=group,
                    claims_by_ref=claims_by_ref,
                ),
                created_at=workflow_command.updated_at,
            )
        schedule = await EnsureWorkItemsScheduled(
            work_item_scheduling_repository
        ).execute(
            EnsureWorkItemsScheduledCommand(
                plans=tuple(
                    _plan(workflow_run_id, batch) for batch in budget_plan.batches
                )
            )
        )
        if schedule.conflict_count:
            raise ValueError("draft claim compaction work item schedule conflict")

        await workflow_unit_of_work.outbox.append_event(
            WorkflowEvent(
                event_id=WorkflowEventId(
                    f"workflow-event:{workflow_run_id}:"
                    f"{KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_CLUSTERS_BUILT.value}:"
                    f"{workflow_command.command_id.value}"
                ),
                event_type=KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_CLUSTERS_BUILT.value,
                workflow_run_id=workflow_run_id,
                payload={
                    "workflow_run_id": workflow_run_id,
                    "candidate_edge_count": persistence.requested_edge_count,
                    "group_count": persistence.requested_group_count,
                    "batch_count": persistence.requested_batch_count,
                    "scheduled_work_item_count": schedule.created_count,
                    "already_scheduled_work_item_count": schedule.already_exists_count,
                    "semantic_meaning": "build hybrid draft claim compaction plan",
                },
                occurred_at=workflow_command.updated_at,
                causation_command_id=workflow_command.command_id,
                correlation_id=workflow_command.command_id.value,
            )
        )
        scheduled_work_item_count = (
            schedule.created_count + schedule.already_exists_count
        )
        if scheduled_work_item_count > 0:
            await workflow_unit_of_work.command_log.append_pending_command(
                _prepare_dispatch_batch_command(
                    workflow_command=workflow_command,
                    workflow_run_id=workflow_run_id,
                    scheduled_work_item_count=scheduled_work_item_count,
                    occurred_at=workflow_command.updated_at,
                )
            )

        await _save_progress_snapshot(
            workflow_unit_of_work=workflow_unit_of_work,
            workflow_run_id=workflow_run_id,
            candidate_edge_count=persistence.requested_edge_count,
            group_count=persistence.requested_group_count,
            batch_count=persistence.requested_batch_count,
            scheduled_work_item_count=schedule.created_count,
            occurred_at=workflow_command.updated_at,
        )
        await workflow_unit_of_work.timeline.append_entry(
            WorkflowTimelineEntry(
                timeline_entry_id=f"workflow-timeline:{workflow_run_id}:DraftClaimCompactionPlanBuilt:{workflow_command.command_id.value}",
                workflow_run_id=workflow_run_id,
                event_type=KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_CLUSTERS_BUILT.value,
                phase=KnowledgeExtractionCanonicalPhase.DRAFT_CLAIM_CLUSTERING.value,
                severity=WorkflowTimelineSeverity.INFO,
                message="Hybrid draft claim compaction plan built",
                payload_summary={
                    "candidate_edge_count": persistence.requested_edge_count,
                    "group_count": persistence.requested_group_count,
                    "batch_count": persistence.requested_batch_count,
                    "scheduled_work_item_count": schedule.created_count,
                },
                occurred_at=workflow_command.updated_at,
                source_ref=workflow_command.command_type,
            )
        )
        await workflow_unit_of_work.command_log.mark_command_completed(
            command_id=workflow_command.command_id,
            completed_at=workflow_command.updated_at,
        )
        return HandleClusterDraftClaimsResult(
            workflow_run_id=workflow_run_id,
            candidate_edge_count=len(edges),
            group_count=len(budget_plan.groups),
            batch_count=len(budget_plan.batches),
            scheduled_work_item_count=schedule.created_count,
            already_scheduled_work_item_count=schedule.already_exists_count,
        )


def _prepare_dispatch_batch_command(
    *,
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    scheduled_work_item_count: int,
    occurred_at,
) -> WorkflowCommand:
    idempotency_key = (
        "draft-claim-compaction-dispatch:"
        f"{workflow_run_id}:initial:{_command_causation_scope(workflow_command)}"
    )
    return WorkflowCommand(
        command_id=WorkflowCommandId(f"workflow-command:{idempotency_key}"),
        command_type=(
            KnowledgeExtractionCanonicalCommandType.PREPARE_DRAFT_CLAIM_COMPACTION_DISPATCH_BATCH.value
        ),
        workflow_run_id=workflow_run_id,
        idempotency_key=WorkflowIdempotencyKey(idempotency_key),
        payload={
            "workflow_run_id": workflow_run_id,
            "work_kind": WORK_KIND.value,
            "scheduled_work_item_count": scheduled_work_item_count,
            "active_model_ref": DRAFT_CLAIM_COMPACTION_ACTIVE_MODEL_REF,
            "worker_ref": DRAFT_CLAIM_COMPACTION_WORKER_REF,
            "caused_by_command_id": workflow_command.command_id.value,
            "llm_dispatch_preparation": {
                "active_model_ref": DRAFT_CLAIM_COMPACTION_ACTIVE_MODEL_REF,
                "requested_items": scheduled_work_item_count,
                "worker_ref": DRAFT_CLAIM_COMPACTION_WORKER_REF,
                "account_capacities": (),
            },
        },
        status=WorkflowCommandStatus.PENDING,
        run_after=occurred_at,
        created_at=occurred_at,
        updated_at=occurred_at,
    )


def _command_causation_scope(workflow_command: WorkflowCommand) -> str:
    return hashlib.sha256(
        workflow_command.command_id.value.encode("utf-8"),
    ).hexdigest()[:12]


def _raw_nodes_for_group(
    *,
    workflow_run_id: str,
    group: DraftClaimCompactionGroupCandidate,
    claims_by_ref: Mapping[str, DraftClaimForCompaction],
):
    return tuple(
        _build_initial_raw_node(
            workflow_run_id=workflow_run_id,
            group_ref=group.group_ref,
            observation_ref=observation_ref,
            estimated_input_tokens=_estimated_raw_claim_tokens(
                claims_by_ref[observation_ref]
            ),
        )
        for observation_ref in group.member_observation_refs
    )


def _build_initial_raw_node(
    *,
    workflow_run_id: str,
    group_ref: str,
    observation_ref: str,
    estimated_input_tokens: int,
) -> DraftClaimCompactionNode:
    return DraftClaimCompactionNode(
        node_ref=raw_claim_node_ref(
            workflow_run_id=workflow_run_id,
            group_ref=group_ref,
            observation_ref=observation_ref,
        ),
        node_kind=DraftClaimCompactionNodeKind.RAW,
        source_claim_refs=(observation_ref,),
        sources=(
            DraftClaimCompactionNodeSource(
                source_ref=observation_ref,
                source_kind=DraftClaimCompactionNodeKind.RAW,
            ),
        ),
        active=True,
        estimated_input_tokens=estimated_input_tokens,
    )


def _estimated_raw_claim_tokens(claim: DraftClaimForCompaction) -> int:
    return max(1, len(claim.embedding_text) // 4)


def _plan(workflow_run_id: str, batch) -> WorkItemSchedulePlan:
    work_item_id = f"claim-compaction:{workflow_run_id}:{batch.batch_ref}"
    return WorkItemSchedulePlan(
        work_item_id=work_item_id,
        work_kind=WORK_KIND,
        idempotency_key=work_item_id,
        payload={
            "workflow_run_id": workflow_run_id,
            "group_ref": batch.group_ref,
            "batch_ref": batch.batch_ref,
            "prompt_variant": batch.prompt_variant,
            "model_id": batch.model_id,
            "source_claim_refs": list(batch.member_observation_refs),
            "llm_capacity_estimate": _batch_capacity_estimate(batch),
        },
    )


def _batch_capacity_estimate(batch) -> dict[str, object]:
    estimated_input_tokens = max(1, batch.estimated_input_tokens)
    reserved_output_tokens = DRAFT_CLAIM_COMPACTION_RESERVED_OUTPUT_TOKENS
    return {
        "estimator": "draft_claim_compaction_batch_budget_policy",
        "estimated_input_tokens": estimated_input_tokens,
        "reserved_output_tokens": reserved_output_tokens,
        "estimated_total_tokens": estimated_input_tokens + reserved_output_tokens,
        "prompt_variant": batch.prompt_variant,
        "model_id": batch.model_id,
    }


async def _save_progress_snapshot(
    *,
    workflow_unit_of_work: WorkflowRuntimeUnitOfWorkPort,
    workflow_run_id: str,
    candidate_edge_count: int,
    group_count: int,
    batch_count: int,
    scheduled_work_item_count: int,
    occurred_at,
) -> None:
    existing = await workflow_unit_of_work.progress_snapshots.get_snapshot(
        workflow_run_id,
    )
    domain_counters = dict(existing.domain_counters) if existing is not None else {}
    domain_counters["draft_claim_compaction_candidate_edge_count"] = (
        candidate_edge_count
    )
    domain_counters["draft_claim_compaction_group_count"] = group_count
    domain_counters["draft_claim_compaction_batch_count"] = batch_count
    domain_counters["draft_claim_compaction_scheduled_work_item_count"] = (
        scheduled_work_item_count
    )
    await workflow_unit_of_work.progress_snapshots.save_snapshot(
        WorkflowProgressSnapshot(
            workflow_run_id=workflow_run_id,
            current_phase=KnowledgeExtractionCanonicalPhase.DRAFT_CLAIM_CLUSTERING.value,
            workflow_status="RUNNING",
            total_work_items=existing.total_work_items if existing is not None else 0,
            scheduled_work_items=(
                existing.scheduled_work_items if existing is not None else 0
            )
            + scheduled_work_item_count,
            running_work_items=0,
            completed_work_items=(
                existing.completed_work_items if existing is not None else 0
            ),
            deferred_work_items=existing.deferred_work_items
            if existing is not None
            else 0,
            retryable_failed_work_items=(
                existing.retryable_failed_work_items if existing is not None else 0
            ),
            terminal_failed_work_items=(
                existing.terminal_failed_work_items if existing is not None else 0
            ),
            blocked_work_items=0,
            domain_counters=domain_counters,
            started_at=existing.started_at if existing is not None else occurred_at,
            updated_at=occurred_at,
            completed_at=existing.completed_at if existing is not None else None,
        ),
    )


def _payload_text(payload: Mapping[str, object], key: str, fallback: str) -> str:
    value = payload.get(key, fallback)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"workflow command payload must include {key}")
    return value
