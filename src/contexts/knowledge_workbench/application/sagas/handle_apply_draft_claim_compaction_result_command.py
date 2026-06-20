from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from src.contexts.execution_runtime.application.ports.work_item_scheduling_repository_port import (
    WorkItemSchedulingRepositoryPort,
)
from src.contexts.execution_runtime.application.use_cases.ensure_work_items_scheduled import (
    EnsureWorkItemsScheduled,
    EnsureWorkItemsScheduledCommand,
    EnsureWorkItemsScheduledResult,
    WorkItemSchedulePlan,
)
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalCommandType,
    KnowledgeExtractionCanonicalEventType,
    KnowledgeExtractionCanonicalPhase,
)
from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_apply_result import (
    DraftClaimCompactionApplyOutputKind,
    DraftClaimCompactionApplyResultCommand,
    DraftClaimCompactionApplyResultOutcome,
    ordered_pair,
)
from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_prompt_contract import (
    DraftClaimCompactionOutputClaim,
    DraftClaimCompactionPromptClaim,
    DraftClaimCompactionPromptPayload,
    DraftClaimReducedRewriteInputClaim,
    DraftClaimReducedRewritePayload,
)
from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_reduction_models import (
    DEGRADED_DRAFT_CLAIM_COMPACTION_MODEL_ID,
    DraftClaimCompactionNode,
    DraftClaimCompactionNodeKind,
    DraftClaimCompactionNextWorkItem,
    DraftClaimCompactionNextWorkItemType,
)
from src.contexts.knowledge_workbench.extraction.application.policies.draft_claim_compaction_output_validator import (
    DraftClaimCompactionOutputValidator,
)
from src.contexts.knowledge_workbench.extraction.application.ports.draft_claim_compaction_reduction_state_repository_port import (
    DraftClaimCompactionReductionStateRepositoryPort,
)
from src.contexts.knowledge_workbench.extraction.application.ports.draft_claim_observation_read_repository_port import (
    DraftClaimObservationReadRepositoryPort,
)
from src.contexts.knowledge_workbench.extraction.application.use_cases.apply_draft_claim_compaction_result import (
    ApplyDraftClaimCompactionResult,
)
from src.contexts.knowledge_workbench.extraction.application.policies.draft_claim_compaction_provider_messages import (
    build_draft_claim_compaction_provider_messages,
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
from src.contexts.workflow_runtime.domain.value_objects.workflow_idempotency_key import (
    WorkflowIdempotencyKey,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_event_id import (
    WorkflowEventId,
)
from src.domain.project_plane.json_types import JsonObject, JsonValue


class DraftClaimCompactionApplyResultUseCasePort(Protocol):
    async def execute(
        self,
        command: DraftClaimCompactionApplyResultCommand,
    ) -> DraftClaimCompactionApplyResultOutcome: ...


WORK_KIND = WorkKind("knowledge_workbench.draft_claim_compaction")
DRAFT_CLAIM_COMPACTION_ACTIVE_MODEL_REF = "openai/gpt-oss-120b"
DRAFT_CLAIM_COMPACTION_WORKER_REF = (
    "knowledge-workbench-draft-claim-compaction-dispatch"
)


@dataclass(frozen=True, slots=True)
class HandleApplyDraftClaimCompactionResultCommand:
    workflow_command: WorkflowCommand


@dataclass(frozen=True, slots=True)
class HandleApplyDraftClaimCompactionResult:
    workflow_run_id: str
    created_node_count: int
    superseded_node_count: int
    comparison_count: int
    next_work_type: str
    scheduled_work_item_count: int
    already_scheduled_work_item_count: int
    appended_next_command_count: int
    next_command_type: str | None


@dataclass(frozen=True, slots=True)
class HandleApplyDraftClaimCompactionResultCommandHandler:
    apply_result_use_case: DraftClaimCompactionApplyResultUseCasePort | None = None

    async def execute(
        self,
        command: HandleApplyDraftClaimCompactionResultCommand,
        *,
        workflow_unit_of_work: WorkflowRuntimeUnitOfWorkPort,
        compaction_reduction_state_repository: (
            DraftClaimCompactionReductionStateRepositoryPort
        ),
        draft_claim_observation_read_repository: DraftClaimObservationReadRepositoryPort,
        work_item_scheduling_repository: WorkItemSchedulingRepositoryPort,
    ) -> HandleApplyDraftClaimCompactionResult:
        workflow_command = command.workflow_command
        if (
            workflow_command.command_type
            != KnowledgeExtractionCanonicalCommandType.APPLY_DRAFT_CLAIM_COMPACTION_RESULT.value
        ):
            raise ValueError(
                "workflow_command command_type must be ApplyDraftClaimCompactionResult"
            )
        if workflow_command.status is not WorkflowCommandStatus.PENDING:
            raise ValueError("workflow_command status must be PENDING")

        apply_command = _apply_command_from_payload(
            workflow_command=workflow_command,
        )
        apply_result_use_case = self.apply_result_use_case
        if apply_result_use_case is None:
            apply_result_use_case = ApplyDraftClaimCompactionResult(
                reduction_state_repository=compaction_reduction_state_repository,
                draft_claim_observation_read_repository=(
                    draft_claim_observation_read_repository
                ),
            )
        outcome = await apply_result_use_case.execute(apply_command)

        schedule = await _schedule_next_work(
            workflow_run_id=apply_command.workflow_run_id,
            group_ref=apply_command.group_ref,
            next_work_item=outcome.next_decision.next_work_item,
            compaction_reduction_state_repository=(
                compaction_reduction_state_repository
            ),
            draft_claim_observation_read_repository=(
                draft_claim_observation_read_repository
            ),
            work_item_scheduling_repository=work_item_scheduling_repository,
        )
        if schedule.conflict_count:
            raise ValueError("draft claim compaction next work item schedule conflict")

        next_workflow_command = _next_workflow_command_after_apply(
            workflow_command=workflow_command,
            apply_command=apply_command,
            outcome=outcome,
            schedule=schedule,
        )
        appended_next_command_count = 0
        next_command_type: str | None = None
        if next_workflow_command is not None:
            await workflow_unit_of_work.command_log.append_pending_command(
                next_workflow_command,
            )
            appended_next_command_count = 1
            next_command_type = next_workflow_command.command_type

        await _append_applied_event(
            workflow_unit_of_work=workflow_unit_of_work,
            workflow_command=workflow_command,
            apply_command=apply_command,
            outcome=outcome,
        )
        await _append_next_event(
            workflow_unit_of_work=workflow_unit_of_work,
            workflow_command=workflow_command,
            apply_command=apply_command,
            outcome=outcome,
            schedule=schedule,
            appended_next_command_count=appended_next_command_count,
        )
        await _save_progress_snapshot(
            workflow_unit_of_work=workflow_unit_of_work,
            workflow_run_id=apply_command.workflow_run_id,
            outcome=outcome,
            schedule=schedule,
            appended_next_command_count=appended_next_command_count,
            occurred_at=workflow_command.updated_at,
        )
        await workflow_unit_of_work.timeline.append_entry(
            WorkflowTimelineEntry(
                timeline_entry_id=(
                    f"workflow-timeline:{apply_command.workflow_run_id}:"
                    f"DraftClaimCompactionResultApplied:"
                    f"{workflow_command.command_id.value}"
                ),
                workflow_run_id=apply_command.workflow_run_id,
                event_type=(
                    KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_RESULT_APPLIED.value
                ),
                phase=KnowledgeExtractionCanonicalPhase.DRAFT_CLAIM_CLUSTERING.value,
                severity=WorkflowTimelineSeverity.INFO,
                message="Draft claim compaction result applied",
                payload_summary=_progress_summary(
                    outcome=outcome,
                    schedule=schedule,
                    appended_next_command_count=appended_next_command_count,
                ),
                occurred_at=workflow_command.updated_at,
                source_ref=workflow_command.command_type,
            )
        )
        await workflow_unit_of_work.timeline.append_entry(
            WorkflowTimelineEntry(
                timeline_entry_id=(
                    f"workflow-timeline:{apply_command.workflow_run_id}:"
                    f"{_next_timeline_suffix(outcome.next_decision.work_type)}:"
                    f"{workflow_command.command_id.value}"
                ),
                workflow_run_id=apply_command.workflow_run_id,
                event_type=_next_event_type(outcome.next_decision.work_type).value,
                phase=KnowledgeExtractionCanonicalPhase.DRAFT_CLAIM_CLUSTERING.value,
                severity=WorkflowTimelineSeverity.INFO,
                message=_next_timeline_message(outcome.next_decision.work_type),
                payload_summary=_progress_summary(
                    outcome=outcome,
                    schedule=schedule,
                    appended_next_command_count=appended_next_command_count,
                ),
                occurred_at=workflow_command.updated_at,
                source_ref=workflow_command.command_type,
            )
        )
        await workflow_unit_of_work.command_log.mark_command_completed(
            command_id=workflow_command.command_id,
            completed_at=workflow_command.updated_at,
        )

        return HandleApplyDraftClaimCompactionResult(
            workflow_run_id=apply_command.workflow_run_id,
            created_node_count=len(outcome.created_node_refs),
            superseded_node_count=len(outcome.superseded_node_refs),
            comparison_count=len(outcome.comparison_refs),
            next_work_type=outcome.next_decision.work_type.value,
            scheduled_work_item_count=schedule.created_count,
            already_scheduled_work_item_count=schedule.already_exists_count,
            appended_next_command_count=appended_next_command_count,
            next_command_type=next_command_type,
        )


def _apply_command_from_payload(
    *,
    workflow_command: WorkflowCommand,
) -> DraftClaimCompactionApplyResultCommand:
    payload = workflow_command.payload
    if not isinstance(payload, Mapping):
        raise ValueError("workflow command payload must be object")

    workflow_run_id = _payload_text(payload, "workflow_run_id")
    if workflow_run_id != workflow_command.workflow_run_id:
        raise ValueError("payload workflow_run_id must match workflow command")

    output_kind = DraftClaimCompactionApplyOutputKind(
        _payload_text(payload, "output_kind")
    )
    compacted_claims_value = payload.get("compacted_claims", [])
    reduced_rewrite_value = payload.get("reduced_rewrite")

    compacted_claims: tuple[DraftClaimCompactionOutputClaim, ...] = ()
    reduced_rewrite = None
    validator = DraftClaimCompactionOutputValidator()
    if output_kind is DraftClaimCompactionApplyOutputKind.COMPACTED_CLAIMS:
        compacted_claims_payload = _compacted_claims_payload(compacted_claims_value)
        input_refs = _source_refs_from_compacted_claims(compacted_claims_payload)
        compacted_claims = validator.validate(
            payload={"compacted_claims": compacted_claims_payload},
            input_claim_refs=input_refs,
        ).compacted_claims
    else:
        reduced_rewrite = validator.validate_reduced_rewrite_output(
            payload=_mapping_value(reduced_rewrite_value, "reduced_rewrite"),
        )

    return DraftClaimCompactionApplyResultCommand(
        workflow_run_id=workflow_run_id,
        group_ref=_payload_text(payload, "group_ref"),
        batch_ref=_payload_text(payload, "batch_ref"),
        work_item_id=_payload_text(payload, "work_item_id"),
        round_index=_payload_int(payload, "round_index"),
        compared_node_refs=_compared_node_refs_from_payload(payload),
        output_kind=output_kind,
        compacted_claims=compacted_claims,
        reduced_rewrite=reduced_rewrite,
        created_at=workflow_command.updated_at,
    )


async def _schedule_next_work(
    *,
    workflow_run_id: str,
    group_ref: str,
    next_work_item: DraftClaimCompactionNextWorkItem,
    compaction_reduction_state_repository: (
        DraftClaimCompactionReductionStateRepositoryPort
    ),
    draft_claim_observation_read_repository: DraftClaimObservationReadRepositoryPort,
    work_item_scheduling_repository: WorkItemSchedulingRepositoryPort,
) -> EnsureWorkItemsScheduledResult:
    if next_work_item.work_type not in {
        DraftClaimCompactionNextWorkItemType.DRAFT_VS_DRAFT,
        DraftClaimCompactionNextWorkItemType.COMPACTED_VS_COMPACTED,
        DraftClaimCompactionNextWorkItemType.MIXED,
        DraftClaimCompactionNextWorkItemType.REDUCED_REWRITE,
    }:
        return await EnsureWorkItemsScheduled(work_item_scheduling_repository).execute(
            EnsureWorkItemsScheduledCommand(plans=())
        )

    batch_ref = _next_batch_ref(
        group_ref=group_ref,
        next_work_item=next_work_item,
    )
    provider_messages = await _provider_messages_for_next_work_item(
        workflow_run_id=workflow_run_id,
        group_ref=group_ref,
        next_work_item=next_work_item,
        compaction_reduction_state_repository=(compaction_reduction_state_repository),
        draft_claim_observation_read_repository=(
            draft_claim_observation_read_repository
        ),
    )
    work_item_id = f"claim-compaction:{workflow_run_id}:{batch_ref}"
    plan = WorkItemSchedulePlan(
        work_item_id=work_item_id,
        work_kind=WORK_KIND,
        idempotency_key=work_item_id,
        payload={
            "workflow_run_id": workflow_run_id,
            "group_ref": group_ref,
            "batch_ref": batch_ref,
            "prompt_variant": next_work_item.work_type.value,
            "model_id": next_work_item.primary_model_id,
            "provider_messages": list(provider_messages),
            "source_node_refs": list(next_work_item.node_refs),
            "compacted_node_refs": list(_compacted_node_refs(next_work_item)),
            "raw_claim_refs": list(_raw_claim_refs(next_work_item)),
            "estimated_prompt_tokens": next_work_item.estimated_prompt_tokens,
            "estimated_completion_tokens": next_work_item.estimated_completion_tokens,
            "estimated_requests": next_work_item.estimated_requests,
            "llm_capacity_estimate": {
                "estimated_input_tokens": next_work_item.estimated_prompt_tokens,
                "reserved_output_tokens": next_work_item.estimated_completion_tokens,
            },
        },
    )
    return await EnsureWorkItemsScheduled(work_item_scheduling_repository).execute(
        EnsureWorkItemsScheduledCommand(plans=(plan,))
    )


async def _provider_messages_for_next_work_item(
    *,
    workflow_run_id: str,
    group_ref: str,
    next_work_item: DraftClaimCompactionNextWorkItem,
    compaction_reduction_state_repository: (
        DraftClaimCompactionReductionStateRepositoryPort
    ),
    draft_claim_observation_read_repository: DraftClaimObservationReadRepositoryPort,
) -> tuple[dict[str, str], ...]:
    state = await compaction_reduction_state_repository.load_planner_state(
        workflow_run_id=workflow_run_id,
        group_ref=group_ref,
    )
    if state is None:
        raise ValueError("draft claim compaction planner state is unavailable")
    nodes_by_ref = {node.node_ref: node for node in state.nodes}

    if next_work_item.work_type is DraftClaimCompactionNextWorkItemType.REDUCED_REWRITE:
        compacted_nodes = tuple(
            _required_active_compacted_node(nodes_by_ref, node_ref)
            for node_ref in next_work_item.node_refs
        )
        payload = DraftClaimReducedRewritePayload(
            compacted_claims=tuple(
                _reduced_rewrite_input_claim(node) for node in compacted_nodes
            )
        ).to_json_dict()
        return build_draft_claim_compaction_provider_messages(
            prompt_file_name="reduced_claim_rewrite.txt",
            payload=payload,
        )

    prompt_claims: list[DraftClaimCompactionPromptClaim] = []
    raw_claim_refs: list[str] = []
    for node_ref in next_work_item.node_refs:
        node = nodes_by_ref.get(node_ref)
        if node is None:
            raw_claim_refs.append(_raw_claim_ref_from_node_ref(node_ref) or node_ref)
            continue
        if not node.active:
            raise ValueError("next compaction work must reference active nodes")
        if node.node_kind is DraftClaimCompactionNodeKind.COMPACTED:
            prompt_claims.append(_compacted_prompt_claim(node))
        else:
            raw_claim_refs.extend(node.source_claim_refs)

    raw_claims = (
        await draft_claim_observation_read_repository.list_by_observation_refs(
            observation_refs=tuple(dict.fromkeys(raw_claim_refs)),
        )
        if raw_claim_refs
        else ()
    )
    raw_by_ref = {claim.observation_ref: claim for claim in raw_claims}
    for raw_claim_ref in raw_claim_refs:
        claim = raw_by_ref.get(raw_claim_ref)
        if claim is None:
            raise ValueError(f"draft claim observation is unavailable: {raw_claim_ref}")
        prompt_claims.append(
            DraftClaimCompactionPromptClaim(
                claim_id=claim.observation_ref,
                claim=claim.claim,
                questions=claim.possible_questions,
            )
        )

    prompt_variant = next_work_item.work_type.value
    payload = DraftClaimCompactionPromptPayload(
        claims=tuple(prompt_claims),
        prompt_variant=prompt_variant,
    ).to_json_dict()
    prompt_file_name = (
        "draft_claim_compaction.txt"
        if next_work_item.work_type
        is DraftClaimCompactionNextWorkItemType.DRAFT_VS_DRAFT
        else "enriched_claim_compaction.txt"
    )
    return build_draft_claim_compaction_provider_messages(
        prompt_file_name=prompt_file_name,
        payload=payload,
    )


def _required_active_compacted_node(
    nodes_by_ref: Mapping[str, DraftClaimCompactionNode],
    node_ref: str,
) -> DraftClaimCompactionNode:
    node = nodes_by_ref.get(node_ref)
    if (
        node is None
        or not node.active
        or node.node_kind is not DraftClaimCompactionNodeKind.COMPACTED
    ):
        raise ValueError("reduced rewrite requires active compacted nodes")
    return node


def _compacted_prompt_claim(
    node: DraftClaimCompactionNode,
) -> DraftClaimCompactionPromptClaim:
    if node.compacted_claim is None:
        raise ValueError("compacted node claim is unavailable")
    return DraftClaimCompactionPromptClaim(
        claim_id=node.node_ref,
        claim=node.compacted_claim,
        questions=(),
    )


def _reduced_rewrite_input_claim(
    node: DraftClaimCompactionNode,
) -> DraftClaimReducedRewriteInputClaim:
    if node.compacted_key is None or node.compacted_claim is None:
        raise ValueError("compacted node rewrite payload is unavailable")
    return DraftClaimReducedRewriteInputClaim(
        key=node.compacted_key,
        claim=node.compacted_claim,
        triples=node.compacted_triples,
    )


def _compacted_node_refs(
    next_work_item: DraftClaimCompactionNextWorkItem,
) -> tuple[str, ...]:
    if next_work_item.work_type in {
        DraftClaimCompactionNextWorkItemType.COMPACTED_VS_COMPACTED,
        DraftClaimCompactionNextWorkItemType.REDUCED_REWRITE,
    }:
        return next_work_item.node_refs

    if next_work_item.work_type is DraftClaimCompactionNextWorkItemType.MIXED:
        return tuple(
            node_ref
            for node_ref in next_work_item.node_refs
            if _raw_claim_ref_from_node_ref(node_ref) is None
        )

    return ()


def _raw_claim_refs(
    next_work_item: DraftClaimCompactionNextWorkItem,
) -> tuple[str, ...]:
    if next_work_item.work_type is DraftClaimCompactionNextWorkItemType.DRAFT_VS_DRAFT:
        return tuple(
            _raw_claim_ref_from_node_ref(node_ref) or node_ref
            for node_ref in next_work_item.node_refs
        )

    if next_work_item.work_type is DraftClaimCompactionNextWorkItemType.MIXED:
        return tuple(
            raw_claim_ref
            for node_ref in next_work_item.node_refs
            if (raw_claim_ref := _raw_claim_ref_from_node_ref(node_ref)) is not None
        )

    return ()


def _raw_claim_ref_from_node_ref(node_ref: str) -> str | None:
    parts = node_ref.split(":", 3)
    if len(parts) != 4:
        return None
    if parts[0] != "raw":
        return None
    raw_claim_ref = parts[3].strip()
    if not raw_claim_ref:
        return None
    return raw_claim_ref


def _next_workflow_command_after_apply(
    *,
    workflow_command: WorkflowCommand,
    apply_command: DraftClaimCompactionApplyResultCommand,
    outcome: DraftClaimCompactionApplyResultOutcome,
    schedule: EnsureWorkItemsScheduledResult,
) -> WorkflowCommand | None:
    work_type = outcome.next_decision.work_type
    if work_type in {
        DraftClaimCompactionNextWorkItemType.DRAFT_VS_DRAFT,
        DraftClaimCompactionNextWorkItemType.COMPACTED_VS_COMPACTED,
        DraftClaimCompactionNextWorkItemType.MIXED,
        DraftClaimCompactionNextWorkItemType.REDUCED_REWRITE,
    }:
        scheduled_count = schedule.created_count + schedule.already_exists_count
        if scheduled_count <= 0:
            return None
        batch_ref = _next_batch_ref(
            group_ref=apply_command.group_ref,
            next_work_item=outcome.next_decision.next_work_item,
        )
        return _prepare_dispatch_batch_command(
            workflow_command=workflow_command,
            workflow_run_id=apply_command.workflow_run_id,
            batch_ref=batch_ref,
            next_work_item=outcome.next_decision.next_work_item,
            scheduled_work_item_count=scheduled_count,
            occurred_at=workflow_command.updated_at,
        )

    if work_type is DraftClaimCompactionNextWorkItemType.DONE:
        return _reconcile_progress_command(
            workflow_command=workflow_command,
            apply_command=apply_command,
            reason="done",
        )

    return None


def _prepare_dispatch_batch_command(
    *,
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    batch_ref: str,
    next_work_item: DraftClaimCompactionNextWorkItem,
    scheduled_work_item_count: int,
    occurred_at,
) -> WorkflowCommand:
    idempotency_key = (
        "draft-claim-compaction-dispatch:"
        f"{workflow_run_id}:{batch_ref}:{_command_causation_scope(workflow_command)}"
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
            "caused_by_command_id": workflow_command.command_id.value,
            "llm_dispatch_preparation": {
                "profile": _next_work_profile_payload(
                    batch_ref=batch_ref,
                    next_work_item=next_work_item,
                ),
                "account_capacities": (),
                "active_model_ref": DRAFT_CLAIM_COMPACTION_ACTIVE_MODEL_REF,
                "requested_items": scheduled_work_item_count,
                "worker_ref": DRAFT_CLAIM_COMPACTION_WORKER_REF,
                "lease_token_prefix": (
                    f"draft-claim-compaction-dispatch:{workflow_run_id}"
                ),
                "lease_ttl_seconds": 300,
            },
        },
        status=WorkflowCommandStatus.PENDING,
        run_after=occurred_at,
        created_at=occurred_at,
        updated_at=occurred_at,
    )


def _next_work_profile_payload(
    *,
    batch_ref: str,
    next_work_item: DraftClaimCompactionNextWorkItem,
) -> dict[str, int | str]:
    estimated_prompt_tokens = max(next_work_item.estimated_prompt_tokens, 1)
    return {
        "profile_id": f"draft_claim_compaction:{batch_ref}",
        "estimated_prompt_tokens": estimated_prompt_tokens,
        "estimated_completion_tokens": next_work_item.estimated_completion_tokens,
        "estimated_requests": next_work_item.estimated_requests,
    }


def _command_causation_scope(workflow_command: WorkflowCommand) -> str:
    return hashlib.sha256(
        workflow_command.command_id.value.encode("utf-8"),
    ).hexdigest()[:12]


def _reconcile_progress_command(
    *,
    workflow_command: WorkflowCommand,
    apply_command: DraftClaimCompactionApplyResultCommand,
    reason: str,
) -> WorkflowCommand:
    idempotency_key = (
        f"draft-claim-compaction-progress:{apply_command.workflow_run_id}:"
        f"{apply_command.group_ref}:{reason}:{apply_command.work_item_id}"
    )
    return WorkflowCommand(
        command_id=WorkflowCommandId(f"workflow-command:{idempotency_key}"),
        command_type=(
            KnowledgeExtractionCanonicalCommandType.RECONCILE_DRAFT_CLAIM_COMPACTION_PROGRESS.value
        ),
        workflow_run_id=apply_command.workflow_run_id,
        idempotency_key=WorkflowIdempotencyKey(idempotency_key),
        payload={
            "workflow_run_id": apply_command.workflow_run_id,
            "group_ref": apply_command.group_ref,
            "caused_by_command_id": workflow_command.command_id.value,
        },
        status=WorkflowCommandStatus.PENDING,
        run_after=workflow_command.updated_at,
        created_at=workflow_command.updated_at,
        updated_at=workflow_command.updated_at,
    )


async def _append_applied_event(
    *,
    workflow_unit_of_work: WorkflowRuntimeUnitOfWorkPort,
    workflow_command: WorkflowCommand,
    apply_command: DraftClaimCompactionApplyResultCommand,
    outcome: DraftClaimCompactionApplyResultOutcome,
) -> None:
    await workflow_unit_of_work.outbox.append_event(
        WorkflowEvent(
            event_id=WorkflowEventId(
                f"workflow-event:{apply_command.workflow_run_id}:"
                f"{KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_RESULT_APPLIED.value}:"
                f"{workflow_command.command_id.value}"
            ),
            event_type=(
                KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_RESULT_APPLIED.value
            ),
            workflow_run_id=apply_command.workflow_run_id,
            payload={
                "workflow_run_id": apply_command.workflow_run_id,
                "group_ref": apply_command.group_ref,
                "batch_ref": apply_command.batch_ref,
                "work_item_id": apply_command.work_item_id,
                "created_node_refs": list(outcome.created_node_refs),
                "superseded_node_refs": list(outcome.superseded_node_refs),
                "comparison_refs": list(outcome.comparison_refs),
                "next_work_type": outcome.next_decision.work_type.value,
            },
            occurred_at=workflow_command.updated_at,
            causation_command_id=workflow_command.command_id,
            correlation_id=workflow_command.command_id.value,
        )
    )


async def _append_next_event(
    *,
    workflow_unit_of_work: WorkflowRuntimeUnitOfWorkPort,
    workflow_command: WorkflowCommand,
    apply_command: DraftClaimCompactionApplyResultCommand,
    outcome: DraftClaimCompactionApplyResultOutcome,
    schedule: EnsureWorkItemsScheduledResult,
    appended_next_command_count: int,
) -> None:
    work_type = outcome.next_decision.work_type
    event_type = _next_event_type(work_type)
    payload: JsonObject = {
        "workflow_run_id": apply_command.workflow_run_id,
        "group_ref": apply_command.group_ref,
        "reason": outcome.next_decision.reason,
        "next_work_type": work_type.value,
        "scheduled_work_item_count": schedule.created_count,
        "already_scheduled_work_item_count": schedule.already_exists_count,
        "appended_next_command_count": appended_next_command_count,
    }
    if work_type is DraftClaimCompactionNextWorkItemType.WAIT_FOR_USER_MODEL_CHOICE:
        resume_work_type = (
            outcome.next_decision.next_work_item.user_choice_resume_work_type
        )
        if resume_work_type is None:
            raise ValueError("waiting user model choice requires resume work type")
        payload.update(
            {
                "primary_model_id": outcome.next_decision.next_work_item.primary_model_id,
                "degraded_candidate_model_id": (
                    outcome.next_decision.next_work_item.degraded_model_id
                    or DEGRADED_DRAFT_CLAIM_COMPACTION_MODEL_ID
                ),
                "group_ref": apply_command.group_ref,
                "node_refs": list(outcome.next_decision.next_work_item.node_refs),
                "resume_work_type": resume_work_type.value,
                "estimated_prompt_tokens": (
                    outcome.next_decision.next_work_item.estimated_prompt_tokens
                ),
                "estimated_completion_tokens": (
                    outcome.next_decision.next_work_item.estimated_completion_tokens
                ),
            }
        )

    await workflow_unit_of_work.outbox.append_event(
        WorkflowEvent(
            event_id=WorkflowEventId(
                f"workflow-event:{apply_command.workflow_run_id}:"
                f"{event_type.value}:{workflow_command.command_id.value}"
            ),
            event_type=event_type.value,
            workflow_run_id=apply_command.workflow_run_id,
            payload=payload,
            occurred_at=workflow_command.updated_at,
            causation_command_id=workflow_command.command_id,
            correlation_id=workflow_command.command_id.value,
        )
    )


async def _save_progress_snapshot(
    *,
    workflow_unit_of_work: WorkflowRuntimeUnitOfWorkPort,
    workflow_run_id: str,
    outcome: DraftClaimCompactionApplyResultOutcome,
    schedule: EnsureWorkItemsScheduledResult,
    appended_next_command_count: int,
    occurred_at,
) -> None:
    existing = await workflow_unit_of_work.progress_snapshots.get_snapshot(
        workflow_run_id,
    )
    domain_counters = dict(existing.domain_counters) if existing is not None else {}
    domain_counters.update(
        {
            "draft_claim_compaction_created_node_count": len(outcome.created_node_refs),
            "draft_claim_compaction_superseded_node_count": len(
                outcome.superseded_node_refs
            ),
            "draft_claim_compaction_comparison_count": len(outcome.comparison_refs),
            "draft_claim_compaction_scheduled_next_work_item_count": (
                schedule.created_count
            ),
            "draft_claim_compaction_already_scheduled_next_work_item_count": (
                schedule.already_exists_count
            ),
            "draft_claim_compaction_appended_next_command_count": (
                appended_next_command_count
            ),
        }
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
            + schedule.created_count,
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
        )
    )


def _progress_summary(
    *,
    outcome: DraftClaimCompactionApplyResultOutcome,
    schedule: EnsureWorkItemsScheduledResult,
    appended_next_command_count: int,
) -> JsonObject:
    return {
        "created_node_count": len(outcome.created_node_refs),
        "superseded_node_count": len(outcome.superseded_node_refs),
        "comparison_count": len(outcome.comparison_refs),
        "next_work_type": outcome.next_decision.work_type.value,
        "scheduled_work_item_count": schedule.created_count,
        "already_scheduled_work_item_count": schedule.already_exists_count,
        "appended_next_command_count": appended_next_command_count,
    }


def _next_event_type(
    work_type: DraftClaimCompactionNextWorkItemType,
) -> KnowledgeExtractionCanonicalEventType:
    if work_type is DraftClaimCompactionNextWorkItemType.WAIT_FOR_USER_MODEL_CHOICE:
        return KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_WAITING_USER_MODEL_CHOICE
    if work_type is DraftClaimCompactionNextWorkItemType.DONE:
        return KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_CLUSTER_DONE
    return (
        KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_NEXT_WORK_SCHEDULED
    )


def _next_timeline_message(work_type: DraftClaimCompactionNextWorkItemType) -> str:
    if work_type is DraftClaimCompactionNextWorkItemType.WAIT_FOR_USER_MODEL_CHOICE:
        return "Draft claim compaction waiting for user model choice"
    if work_type is DraftClaimCompactionNextWorkItemType.DONE:
        return "Draft claim compaction cluster completed"
    return "Draft claim compaction next work scheduled"


def _next_timeline_suffix(work_type: DraftClaimCompactionNextWorkItemType) -> str:
    if work_type is DraftClaimCompactionNextWorkItemType.WAIT_FOR_USER_MODEL_CHOICE:
        return "DraftClaimCompactionWaitingUserModelChoice"
    if work_type is DraftClaimCompactionNextWorkItemType.DONE:
        return "DraftClaimCompactionClusterCompleted"
    return "DraftClaimCompactionNextWorkScheduled"


def _next_batch_ref(
    *,
    group_ref: str,
    next_work_item: DraftClaimCompactionNextWorkItem,
) -> str:
    node_suffix = "--".join(next_work_item.node_refs)
    if not node_suffix:
        raise ValueError("next work item node_refs must be non-empty")
    return f"{group_ref}:{next_work_item.work_type.value}:{node_suffix}"


def _compacted_claims_payload(value: object) -> list[JsonValue]:
    if not isinstance(value, list):
        raise ValueError("compacted_claims must be list")
    return value


def _source_refs_from_compacted_claims(
    compacted_claims: Sequence[JsonValue],
) -> tuple[str, ...]:
    refs: list[str] = []
    for claim in compacted_claims:
        claim_mapping = _mapping_value(claim, "compacted_claim")
        source_refs = claim_mapping.get("source_claim_refs")
        if not isinstance(source_refs, list):
            raise ValueError("compacted_claim source_claim_refs must be list")
        for source_ref in source_refs:
            if not isinstance(source_ref, str) or not source_ref.strip():
                raise ValueError("source_claim_refs must contain non-empty strings")
            refs.append(source_ref)
    return tuple(refs)


def _mapping_value(value: object, field_name: str) -> Mapping[str, JsonValue]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be object")
    result: dict[str, JsonValue] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise ValueError(f"{field_name} keys must be str")
        result[key] = item
    return result


def _payload_text(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"workflow command payload must include {key}")
    return value


def _payload_optional_text(payload: Mapping[str, object], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"workflow command payload {key} must be non-empty text")
    return value


def _compared_node_refs_from_payload(
    payload: Mapping[str, object],
) -> tuple[str, ...]:
    for key in ("compared_node_refs", "source_node_refs"):
        value = payload.get(key)
        if isinstance(value, list) and value:
            refs = tuple(value)
            if all(isinstance(ref, str) and ref.strip() for ref in refs):
                return refs
            raise ValueError(f"{key} must contain non-empty strings")

    left = _payload_optional_text(payload, "left_node_ref")
    right = _payload_optional_text(payload, "right_node_ref")
    if left is None:
        raise ValueError("compared_node_refs are required")
    if right is None:
        return (left,)
    return ordered_pair(left, right)


def _payload_int(payload: Mapping[str, object], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int):
        raise ValueError(f"workflow command payload must include integer {key}")
    return value
