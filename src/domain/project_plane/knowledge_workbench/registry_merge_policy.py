from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from src.domain.project_plane.knowledge_workbench.answer_unit_policy import (
    AnswerUnitMergeDecision,
    AnswerUnitMergePolicyResult,
    decide_answer_unit_merge,
)
from src.domain.project_plane.knowledge_workbench.question_relations import (
    WorkbenchQuestionRelationProposal,
    WorkbenchQuestionRelationType,
    normalize_question_key,
    relation_can_be_applied,
)


class RegistryMergeDecision(StrEnum):
    MERGE_MECHANICALLY = "merge_mechanically"
    RELATE_ONLY = "relate_only"
    KEEP_SEPARATE = "keep_separate"


@dataclass(frozen=True, slots=True)
class RegistryMergePolicyResult:
    decision: RegistryMergeDecision
    question_key: str
    answer_merge: AnswerUnitMergePolicyResult | None = None
    relation: WorkbenchQuestionRelationProposal | None = None

    @property
    def mutates_registry_entry(self) -> bool:
        return self.decision is RegistryMergeDecision.MERGE_MECHANICALLY


def decide_registry_merge(
    *,
    existing_question: str,
    incoming_question: str,
    existing_answer: str,
    incoming_answer: str,
    relation: WorkbenchQuestionRelationProposal | None = None,
) -> RegistryMergePolicyResult:
    existing_key = normalize_question_key(existing_question)
    incoming_key = normalize_question_key(incoming_question)

    if existing_key and existing_key == incoming_key:
        answer_merge = decide_answer_unit_merge(existing_answer, incoming_answer)
        if answer_merge.can_merge_mechanically:
            return RegistryMergePolicyResult(
                decision=RegistryMergeDecision.MERGE_MECHANICALLY,
                question_key=existing_key,
                answer_merge=answer_merge,
            )

    if relation is not None and relation_can_be_applied(relation):
        if relation.relation_type is WorkbenchQuestionRelationType.SAME_AS:
            answer_merge = decide_answer_unit_merge(existing_answer, incoming_answer)
            if answer_merge.decision is not AnswerUnitMergeDecision.DISJOINT:
                return RegistryMergePolicyResult(
                    decision=RegistryMergeDecision.MERGE_MECHANICALLY,
                    question_key=existing_key or incoming_key,
                    answer_merge=answer_merge,
                    relation=relation,
                )

        return RegistryMergePolicyResult(
            decision=RegistryMergeDecision.RELATE_ONLY,
            question_key=existing_key or incoming_key,
            relation=relation,
        )

    return RegistryMergePolicyResult(
        decision=RegistryMergeDecision.KEEP_SEPARATE,
        question_key=existing_key or incoming_key,
    )
