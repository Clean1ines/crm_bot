from __future__ import annotations

from collections.abc import Iterable
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
from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_prompt_contract import (
    DraftClaimCompactionOutputClaim,
)
from src.contexts.knowledge_workbench.extraction.application.policies.draft_claim_compaction_output_enricher import (
    DraftClaimCompactionOutputEnricher,
)
from src.contexts.knowledge_workbench.extraction.application.policies.draft_claim_compaction_reduction_planner_policy import (
    DraftClaimCompactionReductionPlannerPolicy,
)
from src.contexts.knowledge_workbench.extraction.application.ports.draft_claim_compaction_reduction_state_repository_port import (
    DraftClaimCompactionReductionStateRepositoryPort,
)
from src.contexts.knowledge_workbench.extraction.application.ports.draft_claim_observation_read_repository_port import (
    DraftClaimObservationReadRepositoryPort,
)


class DraftClaimCompactionApplyResultError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class ApplyDraftClaimCompactionResult:
    reduction_state_repository: DraftClaimCompactionReductionStateRepositoryPort
    draft_claim_observation_read_repository: (
        DraftClaimObservationReadRepositoryPort | None
    ) = None
    draft_claim_compaction_output_enricher: DraftClaimCompactionOutputEnricher = (
        DraftClaimCompactionOutputEnricher()
    )
    reduction_planner_policy: DraftClaimCompactionReductionPlannerPolicy = (
        DraftClaimCompactionReductionPlannerPolicy()
    )

    async def execute(
        self,
        command: DraftClaimCompactionApplyResultCommand,
    ) -> DraftClaimCompactionApplyResultOutcome:
        compacted_artifacts = ()
        if command.output_kind is DraftClaimCompactionApplyOutputKind.COMPACTED_CLAIMS:
            source_claims = await self._load_source_claims(command.compacted_claims)
            enriched_output = self.draft_claim_compaction_output_enricher.enrich(
                output_claims=command.compacted_claims,
                source_claims=source_claims,
            )
            compacted_artifacts = tuple(
                claim.to_json_dict() for claim in enriched_output.compacted_claims
            )
            await self.reduction_state_repository.apply_compacted_claims_result(
                workflow_run_id=command.workflow_run_id,
                group_ref=command.group_ref,
                batch_ref=command.batch_ref,
                work_item_id=command.work_item_id,
                round_index=command.round_index,
                compacted_claims=enriched_output.compacted_claims,
                compared_node_refs=command.compared_node_refs,
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
            if len(command.compared_node_refs) != 2 or command.reduced_rewrite is None:
                raise DraftClaimCompactionApplyResultError(
                    "reduced rewrite command is incomplete",
                )
            source_node_refs = ordered_pair(*command.compared_node_refs)
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
            compacted_artifacts=compacted_artifacts,
            next_decision=next_decision,
        )

    async def _load_source_claims(
        self,
        compacted_claims: tuple[DraftClaimCompactionOutputClaim, ...],
    ):
        if self.draft_claim_observation_read_repository is None:
            raise DraftClaimCompactionApplyResultError(
                "draft claim observation read repository is required",
            )
        source_claim_refs = _dedupe_preserving_order(
            source_ref
            for compacted_claim in compacted_claims
            for source_ref in compacted_claim.source_claim_refs
        )
        return (
            await self.draft_claim_observation_read_repository.list_by_observation_refs(
                observation_refs=source_claim_refs,
            )
        )


def _node_pairs(node_refs: tuple[str, ...]) -> tuple[tuple[str, str], ...]:
    ordered = tuple(sorted(node_refs))
    pairs: list[tuple[str, str]] = []
    for index, left in enumerate(ordered):
        for right in ordered[index + 1 :]:
            pairs.append((left, right))
    return tuple(pairs)


def _dedupe_preserving_order(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("source claim refs must contain non-empty strings")
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return tuple(result)
