from collections.abc import Mapping

from .intent_topic import (
    FeatureMap,
    feature_risk_detected,
    normalize_intent,
    resolve_topic,
)
from .lifecycle import normalize_lifecycle
from .repeat_detection import (
    REPEAT_ESCALATION_THRESHOLD,
    REPEAT_SOFT_THRESHOLD,
    calculate_repeat_count,
)
from .transitions import lookup_transition

HIGH_INTENT_TOPICS = {"pricing", "product", "integration"}
HANDOFF_LIFECYCLES = {"handoff_to_manager", "angry"}
HANDOFF_INTENTS = {"angry", "handoff_request"}
HANDOFF_TOPICS = {"angry", "handoff"}
LLM_TOPICS = {"support", "feedback", "other"}
MANAGER_CTAS = {"book_consultation", "call_manager"}

PolicyDecision = tuple[str, str, str]
DialogStateMap = Mapping[str, object]


def _previous_dialog_state(dialog_state: DialogStateMap | None) -> DialogStateMap:
    return dialog_state if isinstance(dialog_state, Mapping) else {}


def _human_handoff_decision(lifecycle: str) -> PolicyDecision:
    return lifecycle, "ESCALATE_TO_HUMAN", "call_manager"


def _is_currently_handoff(lifecycle: str) -> bool:
    return lifecycle in HANDOFF_LIFECYCLES


def _is_handoff_signal(intent: str, topic: str) -> bool:
    return intent in HANDOFF_INTENTS or topic in HANDOFF_TOPICS


def _handoff_lifecycle_for_signal(intent: str, topic: str) -> str:
    if intent == "angry" or topic == "angry":
        return "angry"
    return "handoff_to_manager"


def _is_repeat_escalation(topic: str, repeat_count: int) -> bool:
    return topic in HIGH_INTENT_TOPICS and repeat_count >= REPEAT_ESCALATION_THRESHOLD


def _requires_human_handoff(
    lifecycle: str,
    intent: str,
    topic: str,
    repeat_count: int,
    features: FeatureMap | None,
) -> PolicyDecision | None:
    if _is_currently_handoff(lifecycle):
        return _human_handoff_decision(lifecycle)

    if _is_handoff_signal(intent, topic):
        return _human_handoff_decision(_handoff_lifecycle_for_signal(intent, topic))

    if feature_risk_detected(features):
        return _human_handoff_decision("handoff_to_manager")

    if _is_repeat_escalation(topic, repeat_count):
        return _human_handoff_decision("handoff_to_manager")

    return None


def _apply_soft_repeat_progression(
    lifecycle: str,
    topic: str,
    repeat_count: int,
    decision: PolicyDecision,
) -> PolicyDecision:
    if topic not in HIGH_INTENT_TOPICS:
        return decision

    if repeat_count < REPEAT_SOFT_THRESHOLD:
        return decision

    new_lifecycle, current_decision, _cta = decision

    if lifecycle == "cold":
        return "interested", current_decision, "book_consultation"

    if lifecycle == "interested":
        return "warm", current_decision, "book_consultation"

    if lifecycle == "warm":
        return new_lifecycle, current_decision, "call_manager"

    return decision


def _active_client_decision(lifecycle: str, decision: PolicyDecision) -> PolicyDecision:
    if lifecycle != "active_client":
        return decision
    return "active_client", "LLM_GENERATE", "none"


def _llm_topic_decision(topic: str, decision: PolicyDecision) -> PolicyDecision:
    new_lifecycle, current_decision, cta = decision

    if topic not in LLM_TOPICS:
        return decision

    if current_decision == "ESCALATE_TO_HUMAN":
        return decision

    if cta in MANAGER_CTAS:
        return new_lifecycle, "LLM_GENERATE", cta

    return new_lifecycle, "LLM_GENERATE", "none"


def _transition_decision(lifecycle: str, topic: str) -> PolicyDecision:
    return lookup_transition(lifecycle, topic)


def get_decision(
    lifecycle: str | None,
    intent: str | None,
    features: FeatureMap | None = None,
    dialog_state: DialogStateMap | None = None,
) -> PolicyDecision:
    normalized_lifecycle = normalize_lifecycle(lifecycle)
    normalized_intent = normalize_intent(intent)
    topic = resolve_topic(normalized_intent, features)

    previous_dialog_state = _previous_dialog_state(dialog_state)
    repeat_count = calculate_repeat_count(
        previous_dialog_state, normalized_intent, topic
    )

    handoff_decision = _requires_human_handoff(
        normalized_lifecycle,
        normalized_intent,
        topic,
        repeat_count,
        features,
    )
    if handoff_decision is not None:
        return handoff_decision

    decision = _transition_decision(normalized_lifecycle, topic)
    decision = _apply_soft_repeat_progression(
        normalized_lifecycle, topic, repeat_count, decision
    )
    decision = _active_client_decision(normalized_lifecycle, decision)
    decision = _llm_topic_decision(topic, decision)

    return decision
