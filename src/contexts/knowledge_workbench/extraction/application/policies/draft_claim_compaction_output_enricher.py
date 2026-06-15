from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_prompt_contract import (
    DraftClaimCompactionGranularity,
    DraftClaimCompactionOutputClaim,
)
from src.contexts.knowledge_workbench.extraction.application.models.enriched_draft_claim_compaction_output import (
    EnrichedDraftClaimCompactionOutput,
    EnrichedDraftClaimCompactionOutputClaim,
)
from src.contexts.knowledge_workbench.extraction.application.ports.draft_claim_observation_read_repository_port import (
    DraftClaimObservationReadModel,
)


@dataclass(frozen=True, slots=True)
class DraftClaimCompactionOutputEnricher:
    def enrich(
        self,
        *,
        output_claims: tuple[DraftClaimCompactionOutputClaim, ...],
        source_claims: tuple[DraftClaimObservationReadModel, ...],
    ) -> EnrichedDraftClaimCompactionOutput:
        source_claims_by_ref = {
            source_claim.observation_ref: source_claim for source_claim in source_claims
        }
        enriched_claims: list[EnrichedDraftClaimCompactionOutputClaim] = []

        for output_claim in output_claims:
            selected_source_claims = _source_claims_for_output(
                source_claims_by_ref=source_claims_by_ref,
                output_claim=output_claim,
            )
            possible_questions = _dedupe_stripped(
                question
                for source_claim in selected_source_claims
                for question in source_claim.possible_questions
            )
            exclusion_scope_values = _dedupe_stripped(
                source_claim.exclusion_scope for source_claim in selected_source_claims
            )
            evidence_block_values = _dedupe_stripped(
                source_claim.evidence_block for source_claim in selected_source_claims
            )

            enriched_claims.append(
                EnrichedDraftClaimCompactionOutputClaim(
                    key=output_claim.key,
                    claim=output_claim.claim,
                    claim_kind=output_claim.claim_kind,
                    granularity=_final_granularity_from_source_claims(
                        selected_source_claims
                    ),
                    source_claim_refs=output_claim.source_claim_refs,
                    triples=output_claim.triples,
                    merge_decision=output_claim.merge_decision,
                    possible_questions=possible_questions,
                    exclusion_scope="\n".join(exclusion_scope_values),
                    evidence_block="\n\n".join(evidence_block_values),
                )
            )

        return EnrichedDraftClaimCompactionOutput(
            compacted_claims=tuple(enriched_claims),
        )


def _source_claims_for_output(
    *,
    source_claims_by_ref: dict[str, DraftClaimObservationReadModel],
    output_claim: DraftClaimCompactionOutputClaim,
) -> tuple[DraftClaimObservationReadModel, ...]:
    result: list[DraftClaimObservationReadModel] = []
    for source_claim_ref in output_claim.source_claim_refs:
        source_claim = source_claims_by_ref.get(source_claim_ref)
        if source_claim is None:
            raise ValueError("source claim for compaction output is missing")
        result.append(source_claim)
    return tuple(result)


def _final_granularity_from_source_claims(
    source_claims: tuple[DraftClaimObservationReadModel, ...],
) -> DraftClaimCompactionGranularity:
    if not source_claims:
        raise ValueError("source claims must be non-empty")

    granularities: list[DraftClaimCompactionGranularity] = []
    for source_claim in source_claims:
        raw_granularity = source_claim.granularity
        if not isinstance(raw_granularity, str) or not raw_granularity.strip():
            raise ValueError("source claim granularity must be non-empty str")
        try:
            granularities.append(DraftClaimCompactionGranularity(raw_granularity))
        except ValueError as exc:
            raise ValueError(
                "source claim granularity must be atomic or composite"
            ) from exc

    if all(
        granularity is DraftClaimCompactionGranularity.ATOMIC
        for granularity in granularities
    ):
        return DraftClaimCompactionGranularity.ATOMIC
    return DraftClaimCompactionGranularity.COMPOSITE


def _dedupe_stripped(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not isinstance(value, str):
            raise TypeError("enriched text value must be str")
        stripped = value.strip()
        if not stripped:
            continue
        if stripped in seen:
            continue
        seen.add(stripped)
        result.append(stripped)
    return tuple(result)
