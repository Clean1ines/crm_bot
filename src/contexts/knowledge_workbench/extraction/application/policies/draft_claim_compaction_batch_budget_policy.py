from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace

from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_models import (
    DraftClaimCompactionBatchCandidate,
    DraftClaimCompactionGroupCandidate,
    DraftClaimForCompaction,
)


@dataclass(frozen=True, slots=True)
class DraftClaimCompactionBudgetPlan:
    groups: tuple[DraftClaimCompactionGroupCandidate, ...]
    batches: tuple[DraftClaimCompactionBatchCandidate, ...]


@dataclass(frozen=True, slots=True)
class DraftClaimCompactionBatchBudgetPolicy:
    prompt_variant: str = "draft_vs_draft"
    model_id: str = "openai/gpt-oss-120b"
    max_input_tokens: int = 90000
    prompt_reserve_tokens: int = 8000

    def build_batches(
        self,
        claims: tuple[DraftClaimForCompaction, ...],
        groups: tuple[DraftClaimCompactionGroupCandidate, ...],
    ) -> DraftClaimCompactionBudgetPlan:
        by_ref = {claim.observation_ref: claim for claim in claims}
        usable = self.max_input_tokens - self.prompt_reserve_tokens
        planned_groups: list[DraftClaimCompactionGroupCandidate] = []
        batches: list[DraftClaimCompactionBatchCandidate] = []
        for group in groups:
            costs = tuple(
                (ref, _estimate(by_ref[ref])) for ref in group.member_observation_refs
            )
            chunks = _chunks(costs, usable)
            total = sum(cost for _, cost in costs)
            planned_groups.append(
                replace(
                    group, estimated_input_tokens=total, requires_split=len(chunks) > 1
                )
            )
            for index, refs in enumerate(chunks):
                batches.append(
                    DraftClaimCompactionBatchCandidate(
                        batch_ref=_ref(
                            "draft-claim-compaction-batch",
                            group.group_ref,
                            str(index),
                            *refs,
                        ),
                        workflow_run_id=group.workflow_run_id,
                        group_ref=group.group_ref,
                        prompt_variant=self.prompt_variant,
                        model_id=self.model_id,
                        estimated_input_tokens=sum(
                            _estimate(by_ref[ref]) for ref in refs
                        ),
                        member_observation_refs=refs,
                    )
                )
        return DraftClaimCompactionBudgetPlan(tuple(planned_groups), tuple(batches))


def _estimate(claim: DraftClaimForCompaction) -> int:
    return max(1, (len(claim.claim) + len(claim.embedding_text)) // 4 + 40)


def _chunks(
    costs: tuple[tuple[str, int], ...], limit: int
) -> tuple[tuple[str, ...], ...]:
    result: list[tuple[str, ...]] = []
    current: list[str] = []
    current_cost = 0
    for ref, cost in costs:
        if current and current_cost + cost > limit:
            result.append(tuple(current))
            current = []
            current_cost = 0
        current.append(ref)
        current_cost += cost
    if current:
        result.append(tuple(current))
    return tuple(result)


def _ref(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256(":".join(parts).encode("utf-8")).hexdigest()
    return f"{prefix}:{digest}"
