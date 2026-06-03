from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import re


class WorkbenchQuestionRelationType(StrEnum):
    SAME_AS = "same_as"
    EXPANDS = "expands"
    NARROWS = "narrows"
    UMBRELLA = "umbrella"
    CHILD = "child"


class WorkbenchQuestionRelationStrength(StrEnum):
    EXACT = "exact"
    STRONG = "strong"
    WEAK = "weak"


@dataclass(frozen=True, slots=True)
class WorkbenchQuestionRelationProposal:
    source_question_key: str
    target_question_key: str
    relation_type: WorkbenchQuestionRelationType
    strength: WorkbenchQuestionRelationStrength
    evidence_quotes: tuple[str, ...] = ()

    def is_self_reference(self) -> bool:
        return self.source_question_key == self.target_question_key


_WHITESPACE_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^\wа-яё]+", re.IGNORECASE)


def normalize_question_key(value: str) -> str:
    normalized = _PUNCT_RE.sub(" ", str(value or "").casefold())
    return _WHITESPACE_RE.sub(" ", normalized).strip()


def inverse_question_relation_type(
    relation_type: WorkbenchQuestionRelationType,
) -> WorkbenchQuestionRelationType:
    if relation_type is WorkbenchQuestionRelationType.EXPANDS:
        return WorkbenchQuestionRelationType.NARROWS
    if relation_type is WorkbenchQuestionRelationType.NARROWS:
        return WorkbenchQuestionRelationType.EXPANDS
    if relation_type is WorkbenchQuestionRelationType.UMBRELLA:
        return WorkbenchQuestionRelationType.CHILD
    if relation_type is WorkbenchQuestionRelationType.CHILD:
        return WorkbenchQuestionRelationType.UMBRELLA
    return WorkbenchQuestionRelationType.SAME_AS


def is_hierarchical_question_relation(
    relation_type: WorkbenchQuestionRelationType,
) -> bool:
    return relation_type in {
        WorkbenchQuestionRelationType.EXPANDS,
        WorkbenchQuestionRelationType.NARROWS,
        WorkbenchQuestionRelationType.UMBRELLA,
        WorkbenchQuestionRelationType.CHILD,
    }


def relation_proposal_from_questions(
    *,
    source_question: str,
    target_question: str,
    relation_type: WorkbenchQuestionRelationType,
    strength: WorkbenchQuestionRelationStrength,
    evidence_quotes: tuple[str, ...] = (),
) -> WorkbenchQuestionRelationProposal:
    return WorkbenchQuestionRelationProposal(
        source_question_key=normalize_question_key(source_question),
        target_question_key=normalize_question_key(target_question),
        relation_type=relation_type,
        strength=strength,
        evidence_quotes=tuple(
            quote.strip() for quote in evidence_quotes if quote and quote.strip()
        ),
    )


def relation_can_be_applied(proposal: WorkbenchQuestionRelationProposal) -> bool:
    if proposal.is_self_reference():
        return False
    if proposal.relation_type is WorkbenchQuestionRelationType.SAME_AS:
        return proposal.strength in {
            WorkbenchQuestionRelationStrength.EXACT,
            WorkbenchQuestionRelationStrength.STRONG,
        }
    return bool(proposal.evidence_quotes)
