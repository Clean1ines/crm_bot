from __future__ import annotations

from dataclasses import dataclass

from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_prompt_contract import (
    DraftClaimCompactionClaimKind,
    DraftClaimCompactionGranularity,
    DraftClaimCompactionMergeDecision,
    DraftClaimCompactionTriple,
)
from src.domain.project_plane.json_types import JsonObject, JsonValue


@dataclass(frozen=True, slots=True)
class EnrichedDraftClaimCompactionOutputClaim:
    key: str
    claim: str
    claim_kind: DraftClaimCompactionClaimKind
    granularity: DraftClaimCompactionGranularity
    source_claim_refs: tuple[str, ...]
    triples: tuple[DraftClaimCompactionTriple, ...]
    merge_decision: DraftClaimCompactionMergeDecision
    possible_questions: tuple[str, ...]
    exclusion_scope: str
    evidence_block: str

    def __post_init__(self) -> None:
        _require_non_empty_text(self.key, "key")
        _require_non_empty_text(self.claim, "claim")
        object.__setattr__(
            self,
            "claim_kind",
            DraftClaimCompactionClaimKind(self.claim_kind),
        )
        object.__setattr__(
            self,
            "granularity",
            DraftClaimCompactionGranularity(self.granularity),
        )
        _require_unique_non_empty_text_tuple(
            self.source_claim_refs,
            "source_claim_refs",
        )
        _require_triples_tuple(self.triples)
        object.__setattr__(
            self,
            "merge_decision",
            DraftClaimCompactionMergeDecision(self.merge_decision),
        )
        _require_text_tuple(self.possible_questions, "possible_questions")
        if not isinstance(self.exclusion_scope, str):
            raise TypeError("exclusion_scope must be str")
        _require_non_empty_text(self.evidence_block, "evidence_block")

    def to_json_dict(self) -> JsonObject:
        triples_json: list[JsonValue] = [
            triple.to_json_dict() for triple in self.triples
        ]
        return {
            "key": self.key,
            "claim": self.claim,
            "claim_kind": self.claim_kind.value,
            "granularity": self.granularity.value,
            "source_claim_refs": list(self.source_claim_refs),
            "triples": triples_json,
            "merge_decision": self.merge_decision.value,
            "possible_questions": list(self.possible_questions),
            "exclusion_scope": self.exclusion_scope,
            "evidence_block": self.evidence_block,
        }


@dataclass(frozen=True, slots=True)
class EnrichedDraftClaimCompactionOutput:
    compacted_claims: tuple[EnrichedDraftClaimCompactionOutputClaim, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.compacted_claims, tuple):
            raise TypeError("compacted_claims must be tuple")
        for claim in self.compacted_claims:
            if not isinstance(claim, EnrichedDraftClaimCompactionOutputClaim):
                raise TypeError(
                    "compacted_claims must contain "
                    "EnrichedDraftClaimCompactionOutputClaim"
                )

    def to_json_dict(self) -> JsonObject:
        claims_json: list[JsonValue] = [
            claim.to_json_dict() for claim in self.compacted_claims
        ]
        return {"compacted_claims": claims_json}


def _require_non_empty_text(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _require_text_tuple(value: tuple[str, ...], field_name: str) -> None:
    if not isinstance(value, tuple):
        raise TypeError(f"{field_name} must be tuple")
    for item in value:
        _require_non_empty_text(item, field_name)


def _require_unique_non_empty_text_tuple(
    value: tuple[str, ...],
    field_name: str,
) -> None:
    _require_text_tuple(value, field_name)
    if not value:
        raise ValueError(f"{field_name} must be non-empty")
    if len(set(value)) != len(value):
        raise ValueError(f"{field_name} must be unique")


def _require_triples_tuple(value: tuple[DraftClaimCompactionTriple, ...]) -> None:
    if not isinstance(value, tuple):
        raise TypeError("triples must be tuple")
    for triple in value:
        if not isinstance(triple, DraftClaimCompactionTriple):
            raise TypeError("triples must contain DraftClaimCompactionTriple")
