from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from src.domain.project_plane.json_types import JsonObject, JsonValue


class DraftClaimCompactionClaimKind(StrEnum):
    DEFINITION = "definition"
    PROPERTY = "property"
    CAPABILITY = "capability"
    LIMITATION = "limitation"
    RULE = "rule"
    CONDITION = "condition"
    PROCESS = "process"
    LIST = "list"
    COMPARISON = "comparison"
    CRITERION = "criterion"
    EXAMPLE_SET = "example_set"
    VALUE = "value"
    EXCEPTION = "exception"
    OTHER = "other"


class DraftClaimCompactionGranularity(StrEnum):
    ATOMIC = "atomic"
    COMPOSITE = "composite"


class DraftClaimCompactionMergeDecision(StrEnum):
    MERGED = "merged"
    UNMERGED = "unmerged"


class DraftClaimCompactionTriplePredicate(StrEnum):
    IS_A = "is_a"
    HAS_CAPABILITY = "has_capability"
    HAS_PROPERTY = "has_property"
    HAS_VALUE = "has_value"
    HAS_LIMITATION = "has_limitation"
    REQUIRES = "requires"
    SUPPORTS = "supports"
    INTEGRATES_WITH = "integrates_with"
    USED_FOR = "used_for"
    HANDLES = "handles"
    TRANSFERS_TO = "transfers_to"
    PROVIDES = "provides"
    IMPROVES = "improves"
    CHECKS = "checks"
    REMOVES = "removes"
    CREATES = "creates"
    CONNECTS_TO = "connects_to"


@dataclass(frozen=True, slots=True)
class DraftClaimCompactionPromptClaim:
    claim_id: str
    claim: str
    questions: tuple[str, ...]
    exclusion_scope: tuple[str, ...]
    granularity: str

    def __post_init__(self) -> None:
        _require_non_empty_text(self.claim_id, "claim_id")
        _require_non_empty_text(self.claim, "claim")
        _require_text_tuple(self.questions, "questions")
        _require_text_tuple(self.exclusion_scope, "exclusion_scope")
        _require_non_empty_text(self.granularity, "granularity")

    def to_json_dict(self) -> JsonObject:
        return {
            "id": self.claim_id,
            "claim": self.claim,
            "questions": _json_string_list(self.questions),
            "exclusion_scope": _json_string_list(self.exclusion_scope),
            "granularity": self.granularity,
        }


@dataclass(frozen=True, slots=True)
class DraftClaimCompactionPromptPayload:
    claims: tuple[DraftClaimCompactionPromptClaim, ...]
    prompt_variant: str

    def __post_init__(self) -> None:
        if not isinstance(self.claims, tuple):
            raise TypeError("claims must be tuple")
        for claim in self.claims:
            if not isinstance(claim, DraftClaimCompactionPromptClaim):
                raise TypeError(
                    "claims must contain DraftClaimCompactionPromptClaim",
                )
        _require_non_empty_text(self.prompt_variant, "prompt_variant")

    def to_json_dict(self) -> JsonObject:
        claims_json: list[JsonValue] = [claim.to_json_dict() for claim in self.claims]
        return {"claims": claims_json}


@dataclass(frozen=True, slots=True)
class DraftClaimCompactionTriple:
    subject: str
    predicate: DraftClaimCompactionTriplePredicate
    object: str
    qualifiers: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_non_empty_text(self.subject, "subject")
        object.__setattr__(self, "predicate", _triple_predicate(self.predicate))
        _require_non_empty_text(self.object, "object")
        _require_text_tuple(self.qualifiers, "qualifiers")

    def to_json_dict(self) -> JsonObject:
        return {
            "subject": self.subject,
            "predicate": self.predicate.value,
            "object": self.object,
            "qualifiers": _json_string_list(self.qualifiers),
        }


@dataclass(frozen=True, slots=True)
class DraftClaimCompactionOutputClaim:
    key: str
    claim: str
    claim_kind: DraftClaimCompactionClaimKind
    granularity: DraftClaimCompactionGranularity
    source_claim_refs: tuple[str, ...]
    triples: tuple[DraftClaimCompactionTriple, ...]
    merge_decision: DraftClaimCompactionMergeDecision

    def __post_init__(self) -> None:
        _require_non_empty_text(self.key, "key")
        _require_non_empty_text(self.claim, "claim")
        object.__setattr__(self, "claim_kind", _claim_kind(self.claim_kind))
        object.__setattr__(self, "granularity", _granularity(self.granularity))
        _require_text_tuple(self.source_claim_refs, "source_claim_refs")
        if not self.source_claim_refs:
            raise ValueError("source_claim_refs must be non-empty")
        if len(set(self.source_claim_refs)) != len(self.source_claim_refs):
            raise ValueError("source_claim_refs must be unique")
        if not isinstance(self.triples, tuple):
            raise TypeError("triples must be tuple")
        for triple in self.triples:
            if not isinstance(triple, DraftClaimCompactionTriple):
                raise TypeError("triples must contain DraftClaimCompactionTriple")
        object.__setattr__(
            self,
            "merge_decision",
            _merge_decision(self.merge_decision),
        )

    def to_json_dict(self) -> JsonObject:
        triples_json: list[JsonValue] = [
            triple.to_json_dict() for triple in self.triples
        ]
        return {
            "key": self.key,
            "claim": self.claim,
            "claim_kind": self.claim_kind.value,
            "granularity": self.granularity.value,
            "source_claim_refs": _json_string_list(self.source_claim_refs),
            "triples": triples_json,
            "merge_decision": self.merge_decision.value,
        }


@dataclass(frozen=True, slots=True)
class DraftClaimCompactionOutput:
    compacted_claims: tuple[DraftClaimCompactionOutputClaim, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.compacted_claims, tuple):
            raise TypeError("compacted_claims must be tuple")
        for claim in self.compacted_claims:
            if not isinstance(claim, DraftClaimCompactionOutputClaim):
                raise TypeError(
                    "compacted_claims must contain DraftClaimCompactionOutputClaim",
                )

    def to_json_dict(self) -> JsonObject:
        claims_json: list[JsonValue] = [
            claim.to_json_dict() for claim in self.compacted_claims
        ]
        return {"compacted_claims": claims_json}


@dataclass(frozen=True, slots=True)
class DraftClaimReducedRewriteInputClaim:
    key: str
    claim: str
    triples: tuple[DraftClaimCompactionTriple, ...]

    def __post_init__(self) -> None:
        _require_non_empty_text(self.key, "key")
        _require_non_empty_text(self.claim, "claim")
        _require_triples_tuple(self.triples, "triples")

    def to_json_dict(self) -> JsonObject:
        triples_json: list[JsonValue] = [
            triple.to_json_dict() for triple in self.triples
        ]
        return {
            "key": self.key,
            "claim": self.claim,
            "triples": triples_json,
        }


@dataclass(frozen=True, slots=True)
class DraftClaimReducedRewritePayload:
    compacted_claims: tuple[DraftClaimReducedRewriteInputClaim, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.compacted_claims, tuple):
            raise TypeError("compacted_claims must be tuple")
        if not self.compacted_claims:
            raise ValueError("compacted_claims must be non-empty")
        for claim in self.compacted_claims:
            if not isinstance(claim, DraftClaimReducedRewriteInputClaim):
                raise TypeError(
                    "compacted_claims must contain DraftClaimReducedRewriteInputClaim",
                )

    def to_json_dict(self) -> JsonObject:
        claims_json: list[JsonValue] = [
            claim.to_json_dict() for claim in self.compacted_claims
        ]
        return {"compacted_claims": claims_json}


@dataclass(frozen=True, slots=True)
class DraftClaimReducedRewriteOutput:
    key: str
    claim: str
    triples: tuple[DraftClaimCompactionTriple, ...]

    def __post_init__(self) -> None:
        _require_non_empty_text(self.key, "key")
        _require_non_empty_text(self.claim, "claim")
        _require_triples_tuple(self.triples, "triples")

    def to_json_dict(self) -> JsonObject:
        triples_json: list[JsonValue] = [
            triple.to_json_dict() for triple in self.triples
        ]
        return {
            "key": self.key,
            "claim": self.claim,
            "triples": triples_json,
        }


def draft_claim_compaction_allowed_claim_kinds() -> tuple[str, ...]:
    return tuple(kind.value for kind in DraftClaimCompactionClaimKind)


def draft_claim_compaction_allowed_predicates() -> tuple[str, ...]:
    return tuple(predicate.value for predicate in DraftClaimCompactionTriplePredicate)


def _claim_kind(
    value: DraftClaimCompactionClaimKind | str,
) -> DraftClaimCompactionClaimKind:
    try:
        return DraftClaimCompactionClaimKind(value)
    except ValueError as exc:
        raise ValueError("claim_kind is not allowed") from exc


def _granularity(
    value: DraftClaimCompactionGranularity | str,
) -> DraftClaimCompactionGranularity:
    try:
        return DraftClaimCompactionGranularity(value)
    except ValueError as exc:
        raise ValueError("granularity must be atomic or composite") from exc


def _merge_decision(
    value: DraftClaimCompactionMergeDecision | str,
) -> DraftClaimCompactionMergeDecision:
    try:
        return DraftClaimCompactionMergeDecision(value)
    except ValueError as exc:
        raise ValueError("merge_decision must be merged or unmerged") from exc


def _triple_predicate(
    value: DraftClaimCompactionTriplePredicate | str,
) -> DraftClaimCompactionTriplePredicate:
    try:
        return DraftClaimCompactionTriplePredicate(value)
    except ValueError as exc:
        raise ValueError("predicate is not allowed") from exc


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


def _require_triples_tuple(
    value: tuple[DraftClaimCompactionTriple, ...],
    field_name: str,
) -> None:
    if not isinstance(value, tuple):
        raise TypeError(f"{field_name} must be tuple")
    for triple in value:
        if not isinstance(triple, DraftClaimCompactionTriple):
            raise TypeError(f"{field_name} must contain DraftClaimCompactionTriple")


def _json_string_list(values: tuple[str, ...]) -> list[JsonValue]:
    result: list[JsonValue] = []
    result.extend(values)
    return result


def mapping_to_json_object(mapping: Mapping[str, JsonValue]) -> JsonObject:
    return dict(mapping)
