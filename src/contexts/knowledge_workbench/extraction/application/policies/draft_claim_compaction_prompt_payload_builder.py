from __future__ import annotations

from dataclasses import dataclass

from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_models import (
    DraftClaimForCompaction,
)
from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_prompt_contract import (
    DraftClaimCompactionPromptClaim,
    DraftClaimCompactionPromptPayload,
)


@dataclass(frozen=True, slots=True)
class DraftClaimCompactionPromptPayloadBuilder:
    def build_draft_vs_draft_payload(
        self,
        claims: tuple[DraftClaimForCompaction, ...],
    ) -> DraftClaimCompactionPromptPayload:
        if not isinstance(claims, tuple):
            raise TypeError("claims must be tuple")
        if not claims:
            raise ValueError("claims must be non-empty")

        return DraftClaimCompactionPromptPayload(
            claims=tuple(
                DraftClaimCompactionPromptClaim(
                    claim_id=claim.observation_ref,
                    claim=claim.claim,
                    questions=_dedupe_texts(claim.possible_questions),
                    exclusion_scope=_dedupe_texts(claim.exclusion_scope),
                    granularity=claim.granularity,
                )
                for claim in claims
            ),
            prompt_variant="draft_vs_draft",
        )


def _dedupe_texts(values: tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise TypeError("values must be tuple")

    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not isinstance(value, str):
            raise TypeError("values must contain str")
        normalized = value.strip()
        if not normalized:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return tuple(result)
