from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import hashlib
import re


class AnswerUnitMergeDecision(StrEnum):
    EXACT_DUPLICATE = "exact_duplicate"
    CONTAINED_UNION = "contained_union"
    DISJOINT = "disjoint"
    EMPTY = "empty"


@dataclass(frozen=True, slots=True)
class AnswerUnitMergePolicyResult:
    decision: AnswerUnitMergeDecision
    merged_units: tuple[str, ...]
    left_unit_count: int
    right_unit_count: int
    overlap_unit_count: int

    @property
    def can_merge_mechanically(self) -> bool:
        return self.decision in {
            AnswerUnitMergeDecision.EXACT_DUPLICATE,
            AnswerUnitMergeDecision.CONTAINED_UNION,
        }


_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?。！？])\s+")
_WHITESPACE_RE = re.compile(r"\s+")
_WORD_RE = re.compile(r"[\wа-яё]+", re.IGNORECASE)


def normalize_answer_unit(value: str) -> str:
    return _WHITESPACE_RE.sub(" ", str(value or "").strip())


def answer_unit_fingerprint(value: str) -> str:
    normalized = " ".join(_WORD_RE.findall(normalize_answer_unit(value).casefold()))
    if not normalized:
        return ""
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def split_answer_units(value: str) -> tuple[str, ...]:
    text = normalize_answer_unit(value)
    if not text:
        return ()

    line_units = tuple(
        normalize_answer_unit(line)
        for line in str(value).splitlines()
        if normalize_answer_unit(line)
    )
    if len(line_units) > 1:
        return line_units

    sentence_units = tuple(
        normalize_answer_unit(part) for part in _SENTENCE_SPLIT_RE.split(text)
    )
    return tuple(unit for unit in sentence_units if unit)


def decide_answer_unit_merge(
    left: str,
    right: str,
) -> AnswerUnitMergePolicyResult:
    left_units = split_answer_units(left)
    right_units = split_answer_units(right)

    if not left_units and not right_units:
        return AnswerUnitMergePolicyResult(
            decision=AnswerUnitMergeDecision.EMPTY,
            merged_units=(),
            left_unit_count=0,
            right_unit_count=0,
            overlap_unit_count=0,
        )

    left_by_key = {
        answer_unit_fingerprint(unit): unit
        for unit in left_units
        if answer_unit_fingerprint(unit)
    }
    right_by_key = {
        answer_unit_fingerprint(unit): unit
        for unit in right_units
        if answer_unit_fingerprint(unit)
    }

    left_keys = set(left_by_key)
    right_keys = set(right_by_key)
    overlap = left_keys & right_keys

    merged_units = tuple(
        dict.fromkeys(
            (
                *(left_by_key[key] for key in left_keys),
                *(right_by_key[key] for key in right_keys),
            )
        )
    )

    if left_keys == right_keys:
        decision = AnswerUnitMergeDecision.EXACT_DUPLICATE
    elif overlap and (left_keys <= right_keys or right_keys <= left_keys):
        decision = AnswerUnitMergeDecision.CONTAINED_UNION
    else:
        decision = AnswerUnitMergeDecision.DISJOINT

    return AnswerUnitMergePolicyResult(
        decision=decision,
        merged_units=merged_units,
        left_unit_count=len(left_keys),
        right_unit_count=len(right_keys),
        overlap_unit_count=len(overlap),
    )
