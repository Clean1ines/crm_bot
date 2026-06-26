from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from typing import Protocol

from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_models import (
    DraftClaimCompactionBatchCandidate,
    DraftClaimCompactionGroupCandidate,
    DraftClaimForCompaction,
)
from src.contexts.knowledge_workbench.extraction.application.policies.draft_claim_compaction_budget_profile import (
    DRAFT_CLAIM_COMPACTION_ACTIVE_MODEL_REF,
    DRAFT_CLAIM_COMPACTION_PROMPT_VARIANT_DRAFT_VS_DRAFT,
    draft_claim_compaction_artifact_tokens,
    draft_claim_compaction_max_batch_tokens,
)


class DraftClaimCompactionTokenEstimator(Protocol):
    def __call__(self, text: str) -> int: ...


@dataclass(frozen=True, slots=True)
class DraftClaimCompactionBudgetPlan:
    groups: tuple[DraftClaimCompactionGroupCandidate, ...]
    batches: tuple[DraftClaimCompactionBatchCandidate, ...]


@dataclass(frozen=True, slots=True)
class DraftClaimCompactionBatchBudgetPolicy:
    prompt_variant: str = DRAFT_CLAIM_COMPACTION_PROMPT_VARIANT_DRAFT_VS_DRAFT
    model_id: str = DRAFT_CLAIM_COMPACTION_ACTIVE_MODEL_REF
    max_batch_tokens: int | None = None
    token_estimator: DraftClaimCompactionTokenEstimator = (
        draft_claim_compaction_artifact_tokens
    )

    def __post_init__(self) -> None:
        if not isinstance(self.prompt_variant, str) or not self.prompt_variant.strip():
            raise ValueError("prompt_variant must be non-empty")
        if not isinstance(self.model_id, str) or not self.model_id.strip():
            raise ValueError("model_id must be non-empty")
        if self.max_batch_tokens is not None:
            if (
                isinstance(self.max_batch_tokens, bool)
                or not isinstance(self.max_batch_tokens, int)
                or self.max_batch_tokens <= 0
            ):
                raise ValueError("max_batch_tokens must be positive int when provided")
        if not callable(self.token_estimator):
            raise TypeError("token_estimator must be callable")

    def build_batches(
        self,
        claims: tuple[DraftClaimForCompaction, ...],
        groups: tuple[DraftClaimCompactionGroupCandidate, ...],
    ) -> DraftClaimCompactionBudgetPlan:
        by_ref = {claim.observation_ref: claim for claim in claims}
        planned_groups: list[DraftClaimCompactionGroupCandidate] = []
        batches: list[DraftClaimCompactionBatchCandidate] = []

        for group in groups:
            prompt_variant = _prompt_variant_for_batch(
                group=group,
                fallback=self.prompt_variant,
            )
            max_batch_tokens = self._max_batch_tokens_for_variant(prompt_variant)
            costs = tuple(
                (ref, self._estimate(by_ref[ref]))
                for ref in group.member_observation_refs
            )
            chunks = _chunks(costs, max_batch_tokens)
            total = sum(cost for _, cost in costs)
            planned_groups.append(
                replace(
                    group,
                    estimated_input_tokens=total,
                    requires_split=len(chunks) > 1,
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
                        prompt_variant=prompt_variant,
                        model_id=self.model_id,
                        estimated_input_tokens=self._estimate_batch(
                            tuple(by_ref[ref] for ref in refs)
                        ),
                        member_observation_refs=refs,
                    )
                )
        return DraftClaimCompactionBudgetPlan(tuple(planned_groups), tuple(batches))

    def _max_batch_tokens_for_variant(self, prompt_variant: str) -> int:
        if self.max_batch_tokens is not None:
            return self.max_batch_tokens
        return draft_claim_compaction_max_batch_tokens(prompt_variant)

    def _estimate(self, claim: DraftClaimForCompaction) -> int:
        return self.token_estimator(_claim_budget_text(claim))

    def _estimate_batch(self, claims: tuple[DraftClaimForCompaction, ...]) -> int:
        return self.token_estimator(
            "\n\n".join(_claim_budget_text(claim) for claim in claims)
        )


def _prompt_variant_for_batch(
    *,
    group: DraftClaimCompactionGroupCandidate,
    fallback: str,
) -> str:
    if group.member_count == 1:
        return "single_draft_claim_enrichment"
    return fallback


def _claim_budget_text(claim: DraftClaimForCompaction) -> str:
    return "\n".join(
        part
        for part in (
            claim.claim,
            *claim.possible_questions,
            *claim.exclusion_scope,
            claim.granularity,
            claim.embedding_text,
        )
        if part.strip()
    )


def _chunks(
    costs: tuple[tuple[str, int], ...],
    limit: int,
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
