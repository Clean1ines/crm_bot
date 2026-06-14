from __future__ import annotations

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
from src.contexts.workflow_runtime.application.ports.workflow_runtime_unit_of_work_port import (
    WorkflowRuntimeUnitOfWorkPort,
)
from src.contexts.workflow_runtime.domain.entities.workflow_command import (
    WorkflowCommand,
    WorkflowCommandStatus,
)
from src.contexts.workflow_runtime.domain.entities.workflow_event import WorkflowEvent
from src.contexts.workflow_runtime.domain.entities.workflow_timeline_entry import (
    WorkflowTimelineEntry,
    WorkflowTimelineSeverity,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_event_id import (
    WorkflowEventId,
)

WORK_KIND = WorkKind("knowledge_workbench.draft_claim_compaction")


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
        },
    )


def _payload_text(payload: Mapping[str, object], key: str, fallback: str) -> str:
    value = payload.get(key, fallback)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"workflow command payload must include {key}")
    return value
