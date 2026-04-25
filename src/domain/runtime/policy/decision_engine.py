from typing import Any

from .intent_topic import feature_risk_detected, normalize_intent, resolve_topic
from .lifecycle import normalize_lifecycle
from .repeat_detection import REPEAT_ESCALATION_THRESHOLD, REPEAT_SOFT_THRESHOLD, calculate_repeat_count
from .transitions import lookup_transition


def get_decision(
    lifecycle: str | None,
    intent: str | None,
    features: dict[str, Any] | None = None,
    dialog_state: dict[str, Any] | None = None,
) -> tuple[str, str, str]:
    normalized_lifecycle = normalize_lifecycle(lifecycle)
    normalized_intent = normalize_intent(intent)
    topic = resolve_topic(normalized_intent, features)
    previous_dialog_state = dialog_state if isinstance(dialog_state, dict) else {}
    repeat_count = calculate_repeat_count(previous_dialog_state, normalized_intent, topic)

    if normalized_lifecycle in {"handoff_to_manager", "angry"}:
        return normalized_lifecycle, "ESCALATE_TO_HUMAN", "call_manager"

    if normalized_intent in {"angry", "handoff_request"} or topic in {"angry", "handoff"}:
        new_lifecycle = "angry" if normalized_intent == "angry" or topic == "angry" else "handoff_to_manager"
        return new_lifecycle, "ESCALATE_TO_HUMAN", "call_manager"

    if feature_risk_detected(features):
        return "handoff_to_manager", "ESCALATE_TO_HUMAN", "call_manager"

    if repeat_count >= REPEAT_ESCALATION_THRESHOLD and topic in {"pricing", "product", "integration"}:
        return "handoff_to_manager", "ESCALATE_TO_HUMAN", "call_manager"

    new_lifecycle, decision, cta = lookup_transition(normalized_lifecycle, topic)

    if topic in {"pricing", "product", "integration"} and repeat_count >= REPEAT_SOFT_THRESHOLD:
        if normalized_lifecycle == "cold":
            new_lifecycle = "interested"
            cta = "book_consultation"
        elif normalized_lifecycle == "interested":
            new_lifecycle = "warm"
            cta = "book_consultation"
        elif normalized_lifecycle == "warm":
            cta = "call_manager"

    if normalized_lifecycle == "active_client":
        new_lifecycle = "active_client"
        decision = "LLM_GENERATE"
        cta = "none"

    if topic in {"support", "feedback", "other"} and decision != "ESCALATE_TO_HUMAN":
        decision = "LLM_GENERATE"
        if cta not in {"book_consultation", "call_manager"}:
            cta = "none"

    return new_lifecycle, decision, cta
