from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum


JsonObject = dict[str, object]


class FailureStage(StrEnum):
    DOCUMENT_ISSUE = "document_issue"
    ENTRY_COMPILATION_ISSUE = "entry_compilation_issue"
    RETRIEVAL_ISSUE = "retrieval_issue"
    ANSWER_GROUNDING_ISSUE = "answer_grounding_issue"
    NO_ANSWER_POLICY_ISSUE = "no_answer_policy_issue"
    ESCALATION_POLICY_ISSUE = "escalation_policy_issue"
    CONTRADICTION_ISSUE = "contradiction_issue"
    PROMPT_ISSUE = "prompt_issue"
    TECHNICAL_ISSUE = "technical_issue"
    UNKNOWN = "unknown"


class FailureType(StrEnum):
    MISSING_ENTRY = "missing_entry"
    WRONG_ENTRY_TOP1 = "wrong_entry_top1"
    EXPECTED_ENTRY_NOT_FOUND = "expected_entry_not_found"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    UNSUPPORTED_ANSWER = "unsupported_answer"
    HALLUCINATION = "hallucination"
    SHOULD_NOT_ANSWER = "should_not_answer"
    SHOULD_HAVE_ESCALATED = "should_have_escalated"
    CONTRADICTION = "contradiction"
    AMBIGUOUS_SOURCE = "ambiguous_source"
    TECHNICAL_FAILURE = "technical_failure"
    UNKNOWN = "unknown"


class KnowledgeEditActionType(StrEnum):
    ATTACH_QUESTION_TO_ENTRY = "attach_question_to_entry"
    CREATE_ENTRY_FROM_FAILURE = "create_entry_from_failure"
    REBUILD_EMBEDDING = "rebuild_embedding"
    RERUN_EVAL = "rerun_eval"


@dataclass(frozen=True)
class FailureClassification:
    stage: FailureStage = FailureStage.UNKNOWN
    type: FailureType = FailureType.UNKNOWN
    severity: str = "medium"
    root_cause: str = ""
    recommendations: tuple[str, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)

    def to_json(self) -> JsonObject:
        return {
            "stage": self.stage.value,
            "type": self.type.value,
            "severity": self.severity,
            "root_cause": self.root_cause,
            "recommendations": list(self.recommendations),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class KnowledgeEditAction:
    action_type: KnowledgeEditActionType
    reason: str
    target_entry_id: str | None = None
    payload: Mapping[str, object] = field(default_factory=dict)

    def to_json(self) -> JsonObject:
        result: JsonObject = {
            "action_type": self.action_type.value,
            "reason": self.reason,
            "payload": dict(self.payload),
        }
        if self.target_entry_id:
            result["target_entry_id"] = self.target_entry_id
        return result


def _mapping(value: object) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        return value
    return {}


def _string(value: object) -> str:
    return str(value or "").strip()


def _string_tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        text = value.strip()
        return (text,) if text else ()
    if not isinstance(value, Sequence):
        return ()

    result: list[str] = []
    for item in value:
        text = _string(item)
        if text:
            result.append(text)
    return tuple(result)


def _stage(value: object) -> FailureStage:
    normalized = _string(value).lower()
    for item in FailureStage:
        if item.value == normalized:
            return item
    return FailureStage.UNKNOWN


def _failure_type(value: object) -> FailureType:
    normalized = _string(value).lower()
    for item in FailureType:
        if item.value == normalized:
            return item
    return FailureType.UNKNOWN


def failure_classification_from_mapping(
    value: object,
) -> FailureClassification | None:
    payload = _mapping(value)
    if not payload:
        return None

    raw_stage = (
        payload.get("stage")
        or payload.get("failure_stage")
        or payload.get("failed_stage")
    )
    raw_type = (
        payload.get("type") or payload.get("failure_type") or payload.get("failure")
    )

    stage = _stage(raw_stage)
    failure_type = _failure_type(raw_type)

    has_signal = (
        stage != FailureStage.UNKNOWN
        or failure_type != FailureType.UNKNOWN
        or bool(_string(payload.get("root_cause")))
        or bool(_string_tuple(payload.get("recommendations")))
    )
    if not has_signal:
        return None

    return FailureClassification(
        stage=stage,
        type=failure_type,
        severity=_string(payload.get("severity")) or "medium",
        root_cause=_string(
            payload.get("root_cause")
            or payload.get("reason")
            or payload.get("explanation")
        ),
        recommendations=_string_tuple(payload.get("recommendations")),
        metadata={
            key: item
            for key, item in payload.items()
            if key
            not in {
                "stage",
                "failure_stage",
                "failed_stage",
                "type",
                "failure_type",
                "failure",
                "severity",
                "root_cause",
                "reason",
                "explanation",
                "recommendations",
            }
        },
    )


def knowledge_edit_actions_from_value(value: object) -> list[KnowledgeEditAction]:
    if not isinstance(value, Sequence) or isinstance(value, str):
        return []

    actions: list[KnowledgeEditAction] = []
    for item in value:
        payload = _mapping(item)
        if not payload:
            continue

        raw_type = _string(payload.get("action_type") or payload.get("type"))
        action_type = None
        for candidate in KnowledgeEditActionType:
            if candidate.value == raw_type:
                action_type = candidate
                break

        if action_type is None:
            continue

        actions.append(
            KnowledgeEditAction(
                action_type=action_type,
                reason=_string(payload.get("reason")),
                target_entry_id=_string(payload.get("target_entry_id")) or None,
                payload=_mapping(payload.get("payload")),
            )
        )

    return actions


def propose_knowledge_edit_actions(
    *,
    question: object,
    classification: FailureClassification | None,
) -> list[KnowledgeEditAction]:
    if classification is None:
        return []

    expected_entry_ids = tuple(
        str(item).strip()
        for item in getattr(question, "expected_entry_ids", ())
        if str(item).strip()
    )
    question_text = _string(getattr(question, "question", ""))

    actions: list[KnowledgeEditAction] = []

    if expected_entry_ids:
        target_entry_id = expected_entry_ids[0]
        actions.append(
            KnowledgeEditAction(
                action_type=KnowledgeEditActionType.ATTACH_QUESTION_TO_ENTRY,
                target_entry_id=target_entry_id,
                reason=(
                    "Eval failure indicates that this question should improve "
                    "an existing entry retrieval surface."
                ),
                payload={
                    "question": question_text,
                    "failure_stage": classification.stage.value,
                    "failure_type": classification.type.value,
                },
            )
        )
        actions.append(
            KnowledgeEditAction(
                action_type=KnowledgeEditActionType.REBUILD_EMBEDDING,
                target_entry_id=target_entry_id,
                reason=(
                    "Entry retrieval surface may need rebuilt embedding after "
                    "future wording changes."
                ),
                payload={
                    "failure_stage": classification.stage.value,
                    "failure_type": classification.type.value,
                },
            )
        )
    else:
        actions.append(
            KnowledgeEditAction(
                action_type=KnowledgeEditActionType.CREATE_ENTRY_FROM_FAILURE,
                reason=(
                    "Eval failure has no expected entry id; a missing canonical "
                    "entry may be required."
                ),
                payload={
                    "question": question_text,
                    "failure_stage": classification.stage.value,
                    "failure_type": classification.type.value,
                    "root_cause": classification.root_cause,
                },
            )
        )

    actions.append(
        KnowledgeEditAction(
            action_type=KnowledgeEditActionType.RERUN_EVAL,
            reason="Rerun eval after applying a future knowledge edit action.",
            payload={
                "question": question_text,
                "failure_stage": classification.stage.value,
                "failure_type": classification.type.value,
            },
        )
    )

    return actions
