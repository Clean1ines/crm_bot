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
    max_input_tokens: int = 8000
    prompt_reserve_tokens: int = 2050
    input_safety_multiplier: int = 2

    def build_batches(
        self,
        claims: tuple[DraftClaimForCompaction, ...],
        groups: tuple[DraftClaimCompactionGroupCandidate, ...],
    ) -> DraftClaimCompactionBudgetPlan:
        by_ref = {claim.observation_ref: claim for claim in claims}
        usable = (
            self.max_input_tokens - self.prompt_reserve_tokens
        ) // self.input_safety_multiplier
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
            scheduled_chunks = tuple(
                refs for refs in chunks if group.member_count == 1 or len(refs) > 1
            )
            for index, refs in enumerate(scheduled_chunks):
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
                        prompt_variant=_prompt_variant_for_batch(
                            group=group,
                            fallback=self.prompt_variant,
                        ),
                        model_id=self.model_id,
                        estimated_input_tokens=sum(
                            _estimate(by_ref[ref]) for ref in refs
                        ),
                        member_observation_refs=refs,
                    )
                )
        return DraftClaimCompactionBudgetPlan(tuple(planned_groups), tuple(batches))


def _prompt_variant_for_batch(
    *,
    group: DraftClaimCompactionGroupCandidate,
    fallback: str,
) -> str:
    if group.member_count == 1:
        return "single_draft_claim_enrichment"
    return fallback


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
