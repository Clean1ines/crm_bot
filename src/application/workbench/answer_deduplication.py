from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from hashlib import sha256

from src.domain.project_plane.knowledge_workbench.answer_unit_policy import (
    AnswerUnitMergeDecision,
    answer_unit_fingerprint as _domain_answer_unit_fingerprint,
    decide_answer_unit_merge,
    normalize_answer_unit,
    split_answer_units,
)


class WorkbenchAnswerDeduplicationDecision(StrEnum):
    KEEP_SEPARATE = "keep_separate"
    MERGE_EXACT_OR_CONTAINED = "merge_exact_or_contained"


@dataclass(frozen=True, slots=True)
class WorkbenchAnswerDeduplicationCandidate:
    """Workbench-local answer card candidate for deterministic deduplication.

    This is intentionally not the removed compiler candidate graph.
    It is the mechanical node input between ClaimObservation/FactRegistry and
    surface materialization.
    """

    candidate_id: str
    claim: str
    answer: str
    variants: tuple[str, ...] = ()
    evidence_quotes: tuple[str, ...] = ()
    source_refs: tuple[Mapping[str, object], ...] = ()
    metadata: Mapping[str, object] | None = None


@dataclass(frozen=True, slots=True)
class WorkbenchAnswerDeduplicationMerge:
    survivor_candidate_id: str
    absorbed_candidate_ids: tuple[str, ...]
    decision: WorkbenchAnswerDeduplicationDecision
    reason: str
    merged_candidate: WorkbenchAnswerDeduplicationCandidate


@dataclass(frozen=True, slots=True)
class WorkbenchAnswerDeduplicationResult:
    candidates: tuple[WorkbenchAnswerDeduplicationCandidate, ...]
    merges: tuple[WorkbenchAnswerDeduplicationMerge, ...]

    @property
    def retained_count(self) -> int:
        return len(self.candidates)

    @property
    def absorbed_count(self) -> int:
        return sum(len(merge.absorbed_candidate_ids) for merge in self.merges)


@dataclass(frozen=True, slots=True)
class _AnswerUnitMerge:
    answer: str
    strategy: str
    left_unit_count: int
    right_unit_count: int
    merged_unit_count: int


_WORD_RE = re.compile(r"[\wа-яё]+", re.IGNORECASE)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?。！？])\s+")
_WHITESPACE_RE = re.compile(r"\s+")


def deduplicate_workbench_answer_candidates(
    candidates: Sequence[WorkbenchAnswerDeduplicationCandidate],
) -> WorkbenchAnswerDeduplicationResult:
    """Collapse only mechanically safe duplicates.

    This node deliberately does not perform semantic equivalence resolution. It merges
    candidates only when their normalized canonical question is the same and
    their answer units are exact/contained duplicates.
    """

    retained: list[WorkbenchAnswerDeduplicationCandidate] = []
    merges: list[WorkbenchAnswerDeduplicationMerge] = []
    index_by_question_key: dict[str, int] = {}

    for candidate in candidates:
        question_key = question_intent_fingerprint(candidate.claim)

        existing_index = index_by_question_key.get(question_key)
        if existing_index is None:
            index_by_question_key[question_key] = len(retained)
            retained.append(_deduplicated_candidate(candidate))
            continue

        existing = retained[existing_index]
        answer_merge = merge_answer_units_deterministically(
            existing.answer,
            candidate.answer,
        )
        if answer_merge is None:
            retained.append(_deduplicated_candidate(candidate))
            continue

        merged_candidate = _merge_candidates(
            existing,
            candidate,
            merged_answer=answer_merge.answer,
            merge_reason=answer_merge.strategy,
        )
        retained[existing_index] = merged_candidate
        merges.append(
            WorkbenchAnswerDeduplicationMerge(
                survivor_candidate_id=existing.candidate_id,
                absorbed_candidate_ids=(candidate.candidate_id,),
                decision=(
                    WorkbenchAnswerDeduplicationDecision.MERGE_EXACT_OR_CONTAINED
                ),
                reason=answer_merge.strategy,
                merged_candidate=merged_candidate,
            )
        )

    return WorkbenchAnswerDeduplicationResult(
        candidates=tuple(retained),
        merges=tuple(merges),
    )


def question_intent_fingerprint(*values: str) -> str:
    tokens: list[str] = []
    for value in values:
        tokens.extend(_WORD_RE.findall(value.casefold()))

    normalized = " ".join(tokens)
    return sha256(normalized.encode("utf-8")).hexdigest() if normalized else ""


def cleanup_answer_text(value: str) -> str:
    units = _answer_text_units(value)
    seen: set[str] = set()
    retained: list[str] = []

    for unit in units:
        fingerprint = answer_unit_fingerprint(unit)
        if not fingerprint or fingerprint in seen:
            continue
        seen.add(fingerprint)
        retained.append(unit)

    return "\n".join(retained)


def answer_unit_fingerprint(value: str) -> str:
    return _domain_answer_unit_fingerprint(value)


def merge_answer_units_deterministically(
    left: str, right: str
) -> _AnswerUnitMerge | None:
    policy_result = decide_answer_unit_merge(left, right)
    if not policy_result.can_merge_mechanically:
        return None

    left_units = _answer_units_by_fingerprint(left)
    right_units = _answer_units_by_fingerprint(right)
    left_keys = set(left_units)
    right_keys = set(right_units)

    if policy_result.decision is AnswerUnitMergeDecision.EXACT_DUPLICATE:
        merged_units = tuple(left_units.values())
        strategy = "exact_same_answer_units"
    elif left_keys >= right_keys:
        merged_units = tuple(left_units.values())
        strategy = "left_contains_right_answer_units"
    elif right_keys >= left_keys:
        merged_units = tuple(right_units.values())
        strategy = "right_contains_left_answer_units"
    else:
        return None

    return _AnswerUnitMerge(
        answer="\n".join(merged_units),
        strategy=strategy,
        left_unit_count=policy_result.left_unit_count,
        right_unit_count=policy_result.right_unit_count,
        merged_unit_count=len(merged_units),
    )


def _deduplicated_candidate(
    candidate: WorkbenchAnswerDeduplicationCandidate,
) -> WorkbenchAnswerDeduplicationCandidate:
    return replace(
        candidate,
        answer=cleanup_answer_text(candidate.answer),
        variants=_dedupe_text(candidate.variants),
        evidence_quotes=_dedupe_text(candidate.evidence_quotes),
        source_refs=_dedupe_source_refs(candidate.source_refs),
    )


def _merge_candidates(
    left: WorkbenchAnswerDeduplicationCandidate,
    right: WorkbenchAnswerDeduplicationCandidate,
    *,
    merged_answer: str,
    merge_reason: str,
) -> WorkbenchAnswerDeduplicationCandidate:
    metadata = dict(left.metadata or {})
    metadata["workbench_deduplication"] = {
        "strategy": "deterministic_answer_unit_merge",
        "reason": merge_reason,
        "absorbed_candidate_ids": tuple(
            _dedupe_text(
                (
                    *_metadata_text_tuple(metadata, "absorbed_candidate_ids"),
                    right.candidate_id,
                )
            )
        ),
    }

    return WorkbenchAnswerDeduplicationCandidate(
        candidate_id=left.candidate_id,
        claim=left.claim or right.claim,
        answer=cleanup_answer_text(merged_answer),
        variants=_dedupe_text(
            (
                left.claim,
                right.claim,
                *left.variants,
                *right.variants,
            )
        ),
        evidence_quotes=_dedupe_text((*left.evidence_quotes, *right.evidence_quotes)),
        source_refs=_dedupe_source_refs((*left.source_refs, *right.source_refs)),
        metadata=metadata,
    )


def _answer_text_units(value: str) -> tuple[str, ...]:
    return split_answer_units(value)


def _answer_units_by_fingerprint(value: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for unit in _answer_text_units(value):
        fingerprint = answer_unit_fingerprint(unit)
        if fingerprint and fingerprint not in result:
            result[fingerprint] = unit
    return result


def _clean_answer_unit(value: str) -> str:
    return normalize_answer_unit(value)


def _dedupe_text(values: Iterable[object]) -> tuple[str, ...]:
    seen: set[str] = set()
    retained: list[str] = []

    for value in values:
        text = _WHITESPACE_RE.sub(" ", str(value or "").strip())
        if not text:
            continue

        key = text.casefold()
        if key in seen:
            continue

        seen.add(key)
        retained.append(text)

    return tuple(retained)


def _dedupe_source_refs(
    refs: Iterable[Mapping[str, object]],
) -> tuple[Mapping[str, object], ...]:
    seen: set[str] = set()
    retained: list[Mapping[str, object]] = []

    for ref in refs:
        key = _source_ref_key(ref)
        if not key or key in seen:
            continue

        seen.add(key)
        retained.append(dict(ref))

    return tuple(retained)


def _source_ref_key(ref: Mapping[str, object]) -> str:
    stable_items: list[str] = []
    for key in sorted(ref):
        value = ref[key]
        if isinstance(value, (str, int, float, bool)) or value is None:
            stable_items.append(f"{key}={value}")
        else:
            stable_items.append(f"{key}={repr(value)}")
    return "|".join(stable_items)


def _metadata_text_tuple(metadata: Mapping[str, object], key: str) -> tuple[str, ...]:
    value = metadata.get(key)
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(str(item) for item in value if str(item).strip())
    return ()


__all__ = [
    "WorkbenchAnswerDeduplicationCandidate",
    "WorkbenchAnswerDeduplicationDecision",
    "WorkbenchAnswerDeduplicationMerge",
    "WorkbenchAnswerDeduplicationResult",
    "answer_unit_fingerprint",
    "cleanup_answer_text",
    "deduplicate_workbench_answer_candidates",
    "merge_answer_units_deterministically",
    "question_intent_fingerprint",
]
