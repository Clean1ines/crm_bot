from collections.abc import Mapping
from dataclasses import dataclass

from src.domain.runtime.cta import is_pending_cta, normalize_cta
from src.domain.runtime.dialog_state import default_dialog_state
from src.domain.runtime.value_parsing import coerce_int
from .intent_topic import FeatureMap
from .lifecycle import DEFAULT_LIFECYCLE

REPEAT_SOFT_THRESHOLD = 2
REPEAT_ESCALATION_THRESHOLD = 3

ESCALATION_LIFECYCLES = {"handoff_to_manager", "angry"}
HIGH_INTENT_TOPICS = {"pricing", "product", "integration"}

DialogStateMap = Mapping[str, object]
MutableDialogState = dict[str, object]


@dataclass(frozen=True, slots=True)
class RepeatEvaluation:
    count: int
    increment_reason: str | None = None
    reset_reason: str | None = None


def _normalized_previous_value(
    previous_dialog_state: DialogStateMap,
    key: str,
) -> str:
    return str(previous_dialog_state.get(key) or "").strip().lower()


def evaluate_repeat_count(
    previous_dialog_state: DialogStateMap,
    intent: str,
    topic: str,
    *,
    turn_relation: str | None = None,
    is_repeat_like: bool = False,
) -> RepeatEvaluation:
    prev_intent = _normalized_previous_value(previous_dialog_state, "last_intent")
    prev_topic = _normalized_previous_value(previous_dialog_state, "last_topic")
    previous_count = coerce_int(previous_dialog_state.get("repeat_count"), 0)
    normalized_turn_relation = str(turn_relation or "unknown").strip().lower()

    if not intent:
        return RepeatEvaluation(
            0,
            reset_reason="missing_current_intent",
        )

    same_intent = bool(intent and intent == prev_intent)
    same_topic = bool(topic and topic == prev_topic and topic != "other")
    continuation_repeat = (
        normalized_turn_relation == "continuation" and same_intent and same_topic
    )

    if is_repeat_like:
        return RepeatEvaluation(
            max(previous_count, 1) + 1,
            increment_reason="is_repeat_like",
        )

    if continuation_repeat:
        return RepeatEvaluation(
            max(previous_count, 1) + 1,
            increment_reason="continuation_same_intent_topic",
        )

    if normalized_turn_relation == "new_topic":
        return RepeatEvaluation(0, reset_reason="new_topic")

    return RepeatEvaluation(0, reset_reason="no_repeat_evidence")


def calculate_repeat_count(
    previous_dialog_state: DialogStateMap,
    intent: str,
    topic: str,
    *,
    turn_relation: str | None = None,
    is_repeat_like: bool = False,
) -> int:
    return evaluate_repeat_count(
        previous_dialog_state,
        intent,
        topic,
        turn_relation=turn_relation,
        is_repeat_like=is_repeat_like,
    ).count


def _base_dialog_state(
    previous_dialog_state: DialogStateMap,
    lifecycle: str,
) -> MutableDialogState:
    dialog_state: MutableDialogState = dict(default_dialog_state(lifecycle=lifecycle))
    dialog_state.update(previous_dialog_state)
    return dialog_state


def _remember_latest_signals(
    dialog_state: MutableDialogState,
    *,
    intent: str,
    topic: str,
    cta: str,
) -> None:
    if intent:
        dialog_state["last_intent"] = intent

    if topic:
        dialog_state["last_topic"] = topic

    normalized_cta = normalize_cta(cta)
    if is_pending_cta(normalized_cta):
        dialog_state["last_cta"] = normalized_cta


def _initial_lead_status(dialog_state: DialogStateMap, lifecycle: str) -> str:
    lead_status = (
        str(dialog_state.get("lead_status") or lifecycle or DEFAULT_LIFECYCLE)
        .strip()
        .lower()
    )

    if lead_status == "hot":
        return "warm"

    return lead_status


def _is_handoff_required(*, lifecycle: str, decision: str, cta: str) -> bool:
    del cta
    return lifecycle in ESCALATION_LIFECYCLES or decision == "ESCALATE_TO_HUMAN"


def _advance_consultation_status(lead_status: str) -> str:
    if lead_status == "cold":
        return "interested"

    if lead_status == "interested":
        return "warm"

    return lead_status


def _advance_high_intent_topic_status(lead_status: str, repeat_count: int) -> str:
    if repeat_count >= REPEAT_ESCALATION_THRESHOLD:
        return "handoff_to_manager"

    if repeat_count >= REPEAT_SOFT_THRESHOLD and lead_status in {"cold", "interested"}:
        return "warm"

    if lead_status == "cold":
        return "interested"

    return lead_status


def _next_lead_status(
    dialog_state: DialogStateMap,
    *,
    lifecycle: str,
    decision: str,
    cta: str,
    topic: str,
    repeat_count: int,
) -> str:
    lead_status = _initial_lead_status(dialog_state, lifecycle)

    if _is_handoff_required(lifecycle=lifecycle, decision=decision, cta=cta):
        return "handoff_to_manager"

    if lifecycle == "active_client":
        return "active_client"

    if cta == "book_consultation":
        return _advance_consultation_status(lead_status)

    if topic in HIGH_INTENT_TOPICS:
        return _advance_high_intent_topic_status(lead_status, repeat_count)

    return lead_status


def build_dialog_state_update(
    previous_dialog_state: DialogStateMap,
    *,
    intent: str,
    topic: str,
    cta: str,
    lifecycle: str,
    decision: str,
    features: FeatureMap | None = None,
    turn_relation: str | None = None,
    is_repeat_like: bool = False,
) -> MutableDialogState:
    del features

    dialog_state = _base_dialog_state(previous_dialog_state, lifecycle)
    repeat_count = calculate_repeat_count(
        previous_dialog_state,
        intent,
        topic,
        turn_relation=turn_relation,
        is_repeat_like=is_repeat_like,
    )

    dialog_state["repeat_count"] = repeat_count
    _remember_latest_signals(dialog_state, intent=intent, topic=topic, cta=cta)

    dialog_state["lead_status"] = _next_lead_status(
        dialog_state,
        lifecycle=lifecycle,
        decision=decision,
        cta=cta,
        topic=topic,
        repeat_count=repeat_count,
    )
    dialog_state["lifecycle"] = lifecycle

    return dialog_state
