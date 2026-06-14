from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_prompt_contract import (
    DraftClaimCompactionClaimKind,
    DraftClaimCompactionGranularity,
    DraftClaimCompactionMergeDecision,
    DraftClaimCompactionOutput,
    DraftClaimCompactionOutputClaim,
    DraftClaimCompactionTriple,
    DraftClaimCompactionTriplePredicate,
)
from src.domain.project_plane.json_types import JsonValue


class InvalidDraftClaimCompactionOutput(ValueError):
    pass


_OUTPUT_TOP_LEVEL_FIELDS = frozenset({"compacted_claims"})
_OUTPUT_CLAIM_FIELDS = frozenset(
    {
        "key",
        "claim",
        "claim_kind",
        "granularity",
        "source_claim_refs",
        "triples",
        "merge_decision",
    }
)
_TRIPLE_FIELDS = frozenset({"subject", "predicate", "object", "qualifiers"})
_FORBIDDEN_OUTPUT_FIELDS = frozenset(
    {
        "questions",
        "possible_questions",
        "exclusion_scope",
        "evidence",
        "evidence_block",
        "mentions",
        "source_refs",
        "metrics",
        "warnings",
    }
)


@dataclass(frozen=True, slots=True)
class DraftClaimCompactionOutputValidator:
    def validate(
        self,
        *,
        payload: Mapping[str, JsonValue],
        input_claim_refs: tuple[str, ...],
    ) -> DraftClaimCompactionOutput:
        _validate_input_refs(input_claim_refs)

        if not isinstance(payload, Mapping):
            raise InvalidDraftClaimCompactionOutput("payload must be object")

        _reject_forbidden_fields(payload, "top-level output")
        if set(payload.keys()) != _OUTPUT_TOP_LEVEL_FIELDS:
            raise InvalidDraftClaimCompactionOutput(
                "payload must contain exactly compacted_claims",
            )

        compacted_claims_value = payload["compacted_claims"]
        if not isinstance(compacted_claims_value, list):
            raise InvalidDraftClaimCompactionOutput("compacted_claims must be list")

        compacted_claims: list[DraftClaimCompactionOutputClaim] = []
        seen_source_refs: set[str] = set()
        allowed_source_refs = set(input_claim_refs)

        for index, claim_value in enumerate(compacted_claims_value):
            claim = _validate_compacted_claim(
                claim_value=claim_value,
                index=index,
                allowed_source_refs=allowed_source_refs,
                seen_source_refs=seen_source_refs,
            )
            compacted_claims.append(claim)

        missing_refs = tuple(
            ref for ref in input_claim_refs if ref not in seen_source_refs
        )
        if missing_refs:
            raise InvalidDraftClaimCompactionOutput(
                "every input claim ref must appear exactly once",
            )

        return DraftClaimCompactionOutput(compacted_claims=tuple(compacted_claims))


def _validate_compacted_claim(
    *,
    claim_value: JsonValue,
    index: int,
    allowed_source_refs: set[str],
    seen_source_refs: set[str],
) -> DraftClaimCompactionOutputClaim:
    if not isinstance(claim_value, Mapping):
        raise InvalidDraftClaimCompactionOutput(
            f"compacted_claims[{index}] must be object",
        )

    _reject_forbidden_fields(claim_value, f"compacted_claims[{index}]")
    if set(claim_value.keys()) != _OUTPUT_CLAIM_FIELDS:
        raise InvalidDraftClaimCompactionOutput(
            f"compacted_claims[{index}] field set is invalid",
        )

    source_claim_refs = _string_list(
        claim_value["source_claim_refs"],
        f"compacted_claims[{index}].source_claim_refs",
    )
    if not source_claim_refs:
        raise InvalidDraftClaimCompactionOutput("source_claim_refs must be non-empty")

    for ref in source_claim_refs:
        if ref not in allowed_source_refs:
            raise InvalidDraftClaimCompactionOutput(
                "source_claim_refs must contain only input ids",
            )
        if ref in seen_source_refs:
            raise InvalidDraftClaimCompactionOutput(
                "input claim refs must not be duplicated",
            )
        seen_source_refs.add(ref)

    merge_decision = _merge_decision(
        claim_value["merge_decision"],
        f"compacted_claims[{index}].merge_decision",
    )
    if len(source_claim_refs) == 1 and merge_decision is not (
        DraftClaimCompactionMergeDecision.UNMERGED
    ):
        raise InvalidDraftClaimCompactionOutput(
            "single source ref requires merge_decision=unmerged",
        )
    if len(source_claim_refs) > 1 and merge_decision is not (
        DraftClaimCompactionMergeDecision.MERGED
    ):
        raise InvalidDraftClaimCompactionOutput(
            "multiple source refs require merge_decision=merged",
        )

    return DraftClaimCompactionOutputClaim(
        key=_non_empty_string(claim_value["key"], f"compacted_claims[{index}].key"),
        claim=_non_empty_string(
            claim_value["claim"],
            f"compacted_claims[{index}].claim",
        ),
        claim_kind=_claim_kind(
            claim_value["claim_kind"],
            f"compacted_claims[{index}].claim_kind",
        ),
        granularity=_granularity(
            claim_value["granularity"],
            f"compacted_claims[{index}].granularity",
        ),
        source_claim_refs=source_claim_refs,
        triples=_triples(claim_value["triples"], f"compacted_claims[{index}].triples"),
        merge_decision=merge_decision,
    )


def _triples(
    value: JsonValue, field_name: str
) -> tuple[DraftClaimCompactionTriple, ...]:
    if not isinstance(value, list):
        raise InvalidDraftClaimCompactionOutput(f"{field_name} must be list")

    triples: list[DraftClaimCompactionTriple] = []
    for index, item in enumerate(value):
        item_name = f"{field_name}[{index}]"
        if not isinstance(item, Mapping):
            raise InvalidDraftClaimCompactionOutput(f"{item_name} must be object")
        _reject_forbidden_fields(item, item_name)
        if set(item.keys()) != _TRIPLE_FIELDS:
            raise InvalidDraftClaimCompactionOutput(f"{item_name} field set is invalid")
        triples.append(
            DraftClaimCompactionTriple(
                subject=_non_empty_string(item["subject"], f"{item_name}.subject"),
                predicate=_predicate(item["predicate"], f"{item_name}.predicate"),
                object=_non_empty_string(item["object"], f"{item_name}.object"),
                qualifiers=_string_list(item["qualifiers"], f"{item_name}.qualifiers"),
            )
        )
    return tuple(triples)


def _reject_forbidden_fields(
    mapping: Mapping[str, JsonValue],
    location: str,
) -> None:
    forbidden = _FORBIDDEN_OUTPUT_FIELDS.intersection(mapping.keys())
    if forbidden:
        names = ", ".join(sorted(forbidden))
        raise InvalidDraftClaimCompactionOutput(
            f"{location} contains forbidden fields: {names}",
        )


def _validate_input_refs(input_claim_refs: tuple[str, ...]) -> None:
    if not isinstance(input_claim_refs, tuple):
        raise TypeError("input_claim_refs must be tuple")
    if not input_claim_refs:
        raise ValueError("input_claim_refs must be non-empty")
    if len(set(input_claim_refs)) != len(input_claim_refs):
        raise ValueError("input_claim_refs must be unique")
    for ref in input_claim_refs:
        _require_non_empty_text(ref, "input_claim_refs")


def _claim_kind(
    value: JsonValue,
    field_name: str,
) -> DraftClaimCompactionClaimKind:
    if not isinstance(value, str):
        raise InvalidDraftClaimCompactionOutput(f"{field_name} must be str")
    try:
        return DraftClaimCompactionClaimKind(value)
    except ValueError as exc:
        raise InvalidDraftClaimCompactionOutput(
            f"{field_name} is not allowed",
        ) from exc


def _granularity(
    value: JsonValue,
    field_name: str,
) -> DraftClaimCompactionGranularity:
    if not isinstance(value, str):
        raise InvalidDraftClaimCompactionOutput(f"{field_name} must be str")
    try:
        return DraftClaimCompactionGranularity(value)
    except ValueError as exc:
        raise InvalidDraftClaimCompactionOutput(
            f"{field_name} must be atomic or composite",
        ) from exc


def _merge_decision(
    value: JsonValue,
    field_name: str,
) -> DraftClaimCompactionMergeDecision:
    if not isinstance(value, str):
        raise InvalidDraftClaimCompactionOutput(f"{field_name} must be str")
    try:
        return DraftClaimCompactionMergeDecision(value)
    except ValueError as exc:
        raise InvalidDraftClaimCompactionOutput(
            f"{field_name} must be merged or unmerged",
        ) from exc


def _predicate(
    value: JsonValue,
    field_name: str,
) -> DraftClaimCompactionTriplePredicate:
    if not isinstance(value, str):
        raise InvalidDraftClaimCompactionOutput(f"{field_name} must be str")
    try:
        return DraftClaimCompactionTriplePredicate(value)
    except ValueError as exc:
        raise InvalidDraftClaimCompactionOutput(
            f"{field_name} is not allowed",
        ) from exc


def _string_list(value: JsonValue, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise InvalidDraftClaimCompactionOutput(f"{field_name} must be list")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise InvalidDraftClaimCompactionOutput(
                f"{field_name} must contain non-empty strings",
            )
        result.append(item)
    return tuple(result)


def _non_empty_string(value: JsonValue, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidDraftClaimCompactionOutput(f"{field_name} must be non-empty str")
    return value


def _require_non_empty_text(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must contain str")
    if not value.strip():
        raise ValueError(f"{field_name} must contain non-empty strings")
