from __future__ import annotations

from dataclasses import dataclass

from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_apply_result import (
    DraftClaimCompactionApplyOutputKind,
    DraftClaimCompactionApplyResultCommand,
    DraftClaimCompactionApplyResultOutcome,
    compacted_claim_node_ref,
    comparison_ref,
    ordered_pair,
    raw_claim_node_ref,
)
from src.contexts.knowledge_workbench.extraction.application.policies.draft_claim_compaction_reduction_planner_policy import (
    DraftClaimCompactionReductionPlannerPolicy,
)
from src.contexts.knowledge_workbench.extraction.application.ports.draft_claim_compaction_reduction_state_repository_port import (
    DraftClaimCompactionReductionStateRepositoryPort,
)


class DraftClaimCompactionApplyResultError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class ApplyDraftClaimCompactionResult:
    reduction_state_repository: DraftClaimCompactionReductionStateRepositoryPort
    reduction_planner_policy: DraftClaimCompactionReductionPlannerPolicy = (
        DraftClaimCompactionReductionPlannerPolicy()
    )

    async def execute(
        self,
        command: DraftClaimCompactionApplyResultCommand,
    ) -> DraftClaimCompactionApplyResultOutcome:
        if command.output_kind is DraftClaimCompactionApplyOutputKind.COMPACTED_CLAIMS:
            await self.reduction_state_repository.apply_compacted_claims_result(
                workflow_run_id=command.workflow_run_id,
                group_ref=command.group_ref,
                batch_ref=command.batch_ref,
                work_item_id=command.work_item_id,
                round_index=command.round_index,
                compacted_claims=command.compacted_claims,
                created_at=command.created_at,
            )
            created_node_refs = tuple(
                compacted_claim_node_ref(
                    workflow_run_id=command.workflow_run_id,
                    group_ref=command.group_ref,
                    source_claim_refs=claim.source_claim_refs,
                )
                for claim in command.compacted_claims
            )
            superseded_node_refs = tuple(
                raw_claim_node_ref(
                    workflow_run_id=command.workflow_run_id,
                    group_ref=command.group_ref,
                    observation_ref=source_ref,
                )
                for claim in command.compacted_claims
                for source_ref in claim.source_claim_refs
            )
            comparison_refs = tuple(
                comparison_ref(
                    workflow_run_id=command.workflow_run_id,
                    group_ref=command.group_ref,
                    round_index=command.round_index,
                    left_node_ref=left,
                    right_node_ref=right,
                )
                for claim in command.compacted_claims
                for left, right in _node_pairs(
                    tuple(
                        raw_claim_node_ref(
                            workflow_run_id=command.workflow_run_id,
                            group_ref=command.group_ref,
                            observation_ref=source_ref,
                        )
                        for source_ref in claim.source_claim_refs
                    )
                )
            )
        else:
            if command.right_node_ref is None or command.reduced_rewrite is None:
                raise DraftClaimCompactionApplyResultError(
                    "reduced rewrite command is incomplete",
                )
            source_node_refs = ordered_pair(
                command.left_node_ref, command.right_node_ref
            )
            await self.reduction_state_repository.apply_reduced_rewrite_result(
                workflow_run_id=command.workflow_run_id,
                group_ref=command.group_ref,
                batch_ref=command.batch_ref,
                work_item_id=command.work_item_id,
                round_index=command.round_index,
                source_node_refs=source_node_refs,
                rewrite=command.reduced_rewrite,
                created_at=command.created_at,
            )
            created_node_refs = ()
            superseded_node_refs = source_node_refs
            comparison_refs = (
                comparison_ref(
                    workflow_run_id=command.workflow_run_id,
                    group_ref=command.group_ref,
                    round_index=command.round_index,
                    left_node_ref=source_node_refs[0],
                    right_node_ref=source_node_refs[1],
                ),
            )

        state = await self.reduction_state_repository.load_planner_state(
            workflow_run_id=command.workflow_run_id,
            group_ref=command.group_ref,
        )
        if state is None:
            raise DraftClaimCompactionApplyResultError(
                "planner state was not found after applying compaction result",
            )
        next_decision = self.reduction_planner_policy.plan_next_step(state)
        return DraftClaimCompactionApplyResultOutcome(
            created_node_refs=created_node_refs,
            superseded_node_refs=superseded_node_refs,
            comparison_refs=comparison_refs,
            next_decision=next_decision,
        )


def _node_pairs(node_refs: tuple[str, ...]) -> tuple[tuple[str, str], ...]:
    ordered = tuple(sorted(node_refs))
    pairs: list[tuple[str, str]] = []
    for index, left in enumerate(ordered):
        for right in ordered[index + 1 :]:
            pairs.append((left, right))
    return tuple(pairs)
