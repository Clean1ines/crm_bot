from __future__ import annotations

from dataclasses import dataclass

from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_models import (
    DraftClaimForCompaction,
)
from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_prompt_contract import (
    DraftClaimCompactionOutputClaim,
    DraftClaimCompactionPromptClaim,
    DraftClaimCompactionPromptPayload,
    DraftClaimReducedRewriteInputClaim,
    DraftClaimReducedRewritePayload,
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
                )
                for claim in claims
            ),
            prompt_variant="draft_vs_draft",
        )

    def build_single_draft_claim_enrichment_payload(
        self,
        claims: tuple[DraftClaimForCompaction, ...],
    ) -> DraftClaimCompactionPromptPayload:
        if not isinstance(claims, tuple):
            raise TypeError("claims must be tuple")
        if len(claims) != 1:
            raise ValueError("single draft claim enrichment requires exactly one claim")

        return DraftClaimCompactionPromptPayload(
            claims=tuple(
                DraftClaimCompactionPromptClaim(
                    claim_id=claim.observation_ref,
                    claim=claim.claim,
                    questions=_dedupe_texts(claim.possible_questions),
                )
                for claim in claims
            ),
            prompt_variant="single_draft_claim_enrichment",
        )

    def build_reduced_rewrite_payload(
        self,
        compacted_claims: tuple[DraftClaimCompactionOutputClaim, ...],
    ) -> DraftClaimReducedRewritePayload:
        if not isinstance(compacted_claims, tuple):
            raise TypeError("compacted_claims must be tuple")
        if not compacted_claims:
            raise ValueError("compacted_claims must be non-empty")
        for claim in compacted_claims:
            if not isinstance(claim, DraftClaimCompactionOutputClaim):
                raise TypeError(
                    "compacted_claims must contain DraftClaimCompactionOutputClaim",
                )

        return DraftClaimReducedRewritePayload(
            compacted_claims=tuple(
                DraftClaimReducedRewriteInputClaim(
                    key=claim.key,
                    claim=claim.claim,
                    triples=claim.triples,
                )
                for claim in sorted(compacted_claims, key=lambda claim: claim.key)
            )
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
