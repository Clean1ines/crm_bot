"""
Policy engine node for LangGraph pipeline.

This module keeps routing deterministic and adds a compact dialog_state layer
that tracks repeated intent, topic, CTA, and lead status across turns.
"""

from typing import Any, Dict, Optional, Tuple

from src.core.logging import get_logger, log_node_execution
from src.agent.state import AgentState

logger = get_logger(__name__)

# =============================================================================
# NORMALIZATION CONSTANTS
# =============================================================================
VALID_LIFECYCLES = (
    "cold",
    "interested",
    "warm",
    "handoff_to_manager",
    "active_client",
    "angry",
)

VALID_TOPICS = (
    "pricing",
    "product",
    "integration",
    "support",
    "feedback",
    "other",
    "handoff",
    "angry",
)

# Map extractor intents to business topics.
INTENT_TO_TOPIC = {
    "ask_price": "pricing",
    "ask_features": "product",
    "ask_integration": "integration",
    "pricing": "pricing",
    "sales": "product",
    "support": "support",
    "feedback": "feedback",
    "other": "other",
    "angry": "angry",
    "handoff_request": "handoff",
}

# Certain feature names are treated as higher-risk signals.
RISK_FEATURE_KEYS = {
    "frustration",
    "anger",
    "handoff",
    "complaint",
    "chargeback",
    "refund",
}

# Thresholds for repeated questions.
REPEAT_SOFT_THRESHOLD = 2
REPEAT_ESCALATION_THRESHOLD = 3

# =============================================================================
# TRANSITION TABLE
# =============================================================================
# Format: (current_lifecycle, topic) -> (new_lifecycle, decision, cta)
TRANSITIONS = {
    # Cold leads
    ("cold", "pricing"): ("interested", "LLM_GENERATE", "request_demo"),
    ("cold", "product"): ("interested", "LLM_GENERATE", "request_demo"),
    ("cold", "integration"): ("interested", "LLM_GENERATE", "request_demo"),
    ("cold", "support"): ("cold", "LLM_GENERATE", "none"),
    ("cold", "feedback"): ("cold", "LLM_GENERATE", "none"),
    ("cold", "other"): ("cold", "LLM_GENERATE", "none"),

    # Interested leads
    ("interested", "pricing"): ("warm", "LLM_GENERATE", "book_consultation"),
    ("interested", "product"): ("warm", "LLM_GENERATE", "book_consultation"),
    ("interested", "integration"): ("warm", "LLM_GENERATE", "book_consultation"),
    ("interested", "support"): ("interested", "LLM_GENERATE", "none"),
    ("interested", "feedback"): ("interested", "LLM_GENERATE", "none"),
    ("interested", "other"): ("interested", "LLM_GENERATE", "none"),

    # Warm leads
    ("warm", "pricing"): ("warm", "LLM_GENERATE", "call_manager"),
    ("warm", "product"): ("warm", "LLM_GENERATE", "call_manager"),
    ("warm", "integration"): ("warm", "LLM_GENERATE", "call_manager"),
    ("warm", "support"): ("warm", "ESCALATE_TO_HUMAN", "call_manager"),
    ("warm", "feedback"): ("warm", "LLM_GENERATE", "none"),
    ("warm", "other"): ("warm", "LLM_GENERATE", "none"),

    # Active clients
    ("active_client", "pricing"): ("active_client", "LLM_GENERATE", "none"),
    ("active_client", "product"): ("active_client", "LLM_GENERATE", "none"),
    ("active_client", "integration"): ("active_client", "LLM_GENERATE", "none"),
    ("active_client", "support"): ("active_client", "LLM_GENERATE", "none"),
    ("active_client", "feedback"): ("active_client", "LLM_GENERATE", "none"),
    ("active_client", "other"): ("active_client", "LLM_GENERATE", "none"),

    # Handoff state
    ("handoff_to_manager", "pricing"): ("handoff_to_manager", "ESCALATE_TO_HUMAN", "call_manager"),
    ("handoff_to_manager", "product"): ("handoff_to_manager", "ESCALATE_TO_HUMAN", "call_manager"),
    ("handoff_to_manager", "integration"): ("handoff_to_manager", "ESCALATE_TO_HUMAN", "call_manager"),
    ("handoff_to_manager", "support"): ("handoff_to_manager", "ESCALATE_TO_HUMAN", "call_manager"),
    ("handoff_to_manager", "feedback"): ("handoff_to_manager", "ESCALATE_TO_HUMAN", "call_manager"),
    ("handoff_to_manager", "other"): ("handoff_to_manager", "ESCALATE_TO_HUMAN", "call_manager"),

    # Angry state
    ("angry", "pricing"): ("angry", "ESCALATE_TO_HUMAN", "call_manager"),
    ("angry", "product"): ("angry", "ESCALATE_TO_HUMAN", "call_manager"),
    ("angry", "integration"): ("angry", "ESCALATE_TO_HUMAN", "call_manager"),
    ("angry", "support"): ("angry", "ESCALATE_TO_HUMAN", "call_manager"),
    ("angry", "feedback"): ("angry", "ESCALATE_TO_HUMAN", "call_manager"),
    ("angry", "other"): ("angry", "ESCALATE_TO_HUMAN", "call_manager"),

    # Default fallback
    (None, None): (None, "LLM_GENERATE", "none"),
}

# Default values.
DEFAULT_LIFECYCLE = "cold"
DEFAULT_DECISION = "LLM_GENERATE"
DEFAULT_CTA = "none"
DEFAULT_DIALOG_STATE: Dict[str, Any] = {
    "last_intent": None,
    "last_cta": None,
    "last_topic": None,
    "repeat_count": 0,
    "lead_status": DEFAULT_LIFECYCLE,
}


def _coerce_int(value: Any, default: int = 0) -> int:
    """
    Convert a value to int with a safe fallback.

    Args:
        value: Any value that may represent an integer.
        default: Fallback value if conversion fails.

    Returns:
        Integer value or default.
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalize_lifecycle(lifecycle: Optional[str]) -> str:
    """
    Normalize lifecycle values to the supported lifecycle set.

    Args:
        lifecycle: Raw lifecycle string.

    Returns:
        Normalized lifecycle.
    """
    value = (lifecycle or "").strip().lower()
    if value == "hot":
        # Backward compatibility with older states.
        return "warm"

    if value in VALID_LIFECYCLES:
        return value

    return DEFAULT_LIFECYCLE


def _normalize_intent(intent: Optional[str]) -> str:
    """
    Normalize intent labels coming from the intent extractor.

    Args:
        intent: Raw intent string.

    Returns:
        Canonical intent string.
    """
    value = (intent or "").strip().lower()
    if not value:
        return "other"

    if value in INTENT_TO_TOPIC:
        return value

    if value in {"pricing", "sales", "support", "feedback", "other", "angry", "handoff_request"}:
        return value

    if value in {"ask_price", "price", "cost", "pricing_question"}:
        return "ask_price"

    if value in {"ask_features", "features", "product", "what_you_do"}:
        return "ask_features"

    if value in {"ask_integration", "integration", "crm", "webhook"}:
        return "ask_integration"

    return "other"


def _resolve_topic(intent: Optional[str], features: Optional[Dict[str, Any]] = None) -> str:
    """
    Resolve a business topic from intent and optional features.

    Args:
        intent: Canonical intent label.
        features: Optional feature dictionary from the extractor.

    Returns:
        Canonical topic.
    """
    if isinstance(features, dict):
        topic = features.get("topic")
        if isinstance(topic, str):
            topic_value = topic.strip().lower()
            if topic_value in VALID_TOPICS:
                return topic_value
            if topic_value in INTENT_TO_TOPIC:
                mapped = INTENT_TO_TOPIC[topic_value]
                if mapped in VALID_TOPICS:
                    return mapped

    normalized_intent = _normalize_intent(intent)
    topic = INTENT_TO_TOPIC.get(normalized_intent, normalized_intent)

    if topic in VALID_TOPICS:
        return topic

    return "other"


def _feature_risk_detected(features: Optional[Dict[str, Any]]) -> bool:
    """
    Detect high-risk feature signals that should bias the policy toward escalation.

    Args:
        features: Feature dictionary from the extractor.

    Returns:
        True if a high-risk signal is present, otherwise False.
    """
    if not isinstance(features, dict):
        return False

    for key, value in features.items():
        if key not in RISK_FEATURE_KEYS:
            continue

        if isinstance(value, (int, float)) and float(value) >= 0.8:
            return True

        if isinstance(value, dict):
            for nested_value in value.values():
                if isinstance(nested_value, (int, float)) and float(nested_value) >= 0.8:
                    return True

    return False


def _extract_dialog_state(state: AgentState) -> Dict[str, Any]:
    """
    Extract dialog_state from current state or from loaded user memory.

    Expected memory shapes:
        state["dialog_state"] = {...}
        state["user_memory"]["dialog_state"] = [{"key": "dialog_state", "value": {...}}]

    Args:
        state: Current agent state.

    Returns:
        Normalized dialog_state dictionary.
    """
    raw_dialog_state = state.get("dialog_state")
    if isinstance(raw_dialog_state, dict):
        dialog_state = dict(DEFAULT_DIALOG_STATE)
        dialog_state.update(raw_dialog_state)
        return dialog_state

    memory = state.get("user_memory") or {}
    dialog_items = memory.get("dialog_state") or []

    for item in dialog_items:
        if not isinstance(item, dict):
            continue

        value = item.get("value")
        if isinstance(value, dict):
            dialog_state = dict(DEFAULT_DIALOG_STATE)
            dialog_state.update(value)
            return dialog_state

    return dict(DEFAULT_DIALOG_STATE)


def _calculate_repeat_count(
    previous_dialog_state: Dict[str, Any],
    intent: str,
    topic: str,
) -> int:
    """
    Calculate how many times the same intent/topic has repeated in a row.

    Args:
        previous_dialog_state: Previously stored dialog state.
        intent: Current canonical intent.
        topic: Current canonical topic.

    Returns:
        Updated repeat count.
    """
    prev_intent = str(previous_dialog_state.get("last_intent") or "").strip().lower()
    prev_topic = str(previous_dialog_state.get("last_topic") or "").strip().lower()
    previous_count = _coerce_int(previous_dialog_state.get("repeat_count"), 0)

    if not intent:
        return previous_count

    if intent == prev_intent or topic == prev_topic:
        return previous_count + 1

    return 1


def _build_dialog_state_update(
    previous_dialog_state: Dict[str, Any],
    *,
    intent: str,
    topic: str,
    cta: str,
    lifecycle: str,
    decision: str,
    features: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Build the next dialog_state snapshot.

    Args:
        previous_dialog_state: Previously stored dialog state.
        intent: Current canonical intent.
        topic: Current canonical topic.
        cta: Current CTA.
        lifecycle: Current lifecycle after policy decision.
        decision: Final decision.
        features: Optional extracted features.

    Returns:
        Updated dialog_state dictionary.
    """
    dialog_state = dict(DEFAULT_DIALOG_STATE)
    dialog_state.update(previous_dialog_state or {})

    repeat_count = _calculate_repeat_count(previous_dialog_state, intent, topic)
    dialog_state["repeat_count"] = repeat_count

    if intent:
        dialog_state["last_intent"] = intent

    if topic:
        dialog_state["last_topic"] = topic

    if cta and cta != "none":
        dialog_state["last_cta"] = cta

    # Lead status is a compact lifecycle-style marker for quick decisioning.
    lead_status = str(dialog_state.get("lead_status") or lifecycle or DEFAULT_LIFECYCLE).strip().lower()
    if lead_status == "hot":
        lead_status = "warm"

    if lifecycle in {"handoff_to_manager", "angry"} or decision == "ESCALATE_TO_HUMAN":
        lead_status = "handoff_to_manager"
    elif lifecycle == "active_client":
        lead_status = "active_client"
    elif cta == "call_manager":
        lead_status = "handoff_to_manager"
    elif cta in {"request_demo", "book_consultation"}:
        if lead_status == "cold":
            lead_status = "interested"
        elif lead_status == "interested":
            lead_status = "warm"
    elif topic in {"pricing", "product", "integration"}:
        if repeat_count >= REPEAT_ESCALATION_THRESHOLD:
            lead_status = "handoff_to_manager"
        elif repeat_count >= REPEAT_SOFT_THRESHOLD and lead_status in {"cold", "interested"}:
            lead_status = "warm"
        elif lead_status == "cold":
            lead_status = "interested"

    dialog_state["lead_status"] = lead_status
    dialog_state["lifecycle"] = lifecycle

    return dialog_state


def _lookup_transition(lifecycle: str, topic: str) -> Tuple[str, str, str]:
    """
    Resolve a transition from the transition table.

    Args:
        lifecycle: Current lifecycle.
        topic: Current topic.

    Returns:
        Tuple of (new_lifecycle, decision, cta).
    """
    return TRANSITIONS.get(
        (lifecycle, topic),
        TRANSITIONS.get((lifecycle, "other"), TRANSITIONS.get((None, None), (None, DEFAULT_DECISION, DEFAULT_CTA))),
    )


def get_decision(
    lifecycle: Optional[str],
    intent: Optional[str],
    features: Optional[Dict[str, Any]] = None,
    dialog_state: Optional[Dict[str, Any]] = None,
) -> tuple[str, str, str]:
    """
    Determine decision, new lifecycle, and CTA based on current state.

    Args:
        lifecycle: Current lifecycle stage.
        intent: Detected intent from the intent extractor.
        features: Optional extracted features.
        dialog_state: Optional previously stored dialog_state.

    Returns:
        Tuple of (new_lifecycle, decision, cta).
    """
    normalized_lifecycle = _normalize_lifecycle(lifecycle)
    normalized_intent = _normalize_intent(intent)
    topic = _resolve_topic(normalized_intent, features)
    previous_dialog_state = dialog_state if isinstance(dialog_state, dict) else {}
    repeat_count = _calculate_repeat_count(previous_dialog_state, normalized_intent, topic)

    logger.debug(
        "Policy input normalized",
        extra={
            "lifecycle": normalized_lifecycle,
            "intent": normalized_intent,
            "topic": topic,
            "repeat_count": repeat_count,
        },
    )

    # Hard safety / human handoff conditions.
    if normalized_lifecycle in {"handoff_to_manager", "angry"}:
        return normalized_lifecycle, "ESCALATE_TO_HUMAN", "call_manager"

    if normalized_intent in {"angry", "handoff_request"} or topic in {"angry", "handoff"}:
        new_lifecycle = "angry" if normalized_intent == "angry" or topic == "angry" else "handoff_to_manager"
        return new_lifecycle, "ESCALATE_TO_HUMAN", "call_manager"

    if _feature_risk_detected(features):
        logger.debug("High-risk feature signal detected; escalating")
        return "handoff_to_manager", "ESCALATE_TO_HUMAN", "call_manager"

    # Repeated asks about product/pricing/integration should become more direct.
    if repeat_count >= REPEAT_ESCALATION_THRESHOLD and topic in {"pricing", "product", "integration"}:
        return "handoff_to_manager", "ESCALATE_TO_HUMAN", "call_manager"

    # Base transition table.
    new_lifecycle, decision, cta = _lookup_transition(normalized_lifecycle, topic)

    # Add a bit more pressure on repeated sales conversations.
    if topic in {"pricing", "product", "integration"} and repeat_count >= REPEAT_SOFT_THRESHOLD:
        if normalized_lifecycle == "cold":
            new_lifecycle = "interested"
            cta = "request_demo"
        elif normalized_lifecycle == "interested":
            new_lifecycle = "warm"
            cta = "book_consultation"
        elif normalized_lifecycle == "warm":
            cta = "call_manager"

    # Keep active clients stable.
    if normalized_lifecycle == "active_client":
        new_lifecycle = "active_client"
        decision = "LLM_GENERATE"
        cta = "none"

    # Always prefer a simple answer path for support/feedback.
    if topic in {"support", "feedback", "other"} and decision != "ESCALATE_TO_HUMAN":
        decision = "LLM_GENERATE"
        if cta not in {"request_demo", "book_consultation", "call_manager"}:
            cta = "none"

    logger.debug(
        "Policy transition resolved",
        extra={
            "lifecycle": normalized_lifecycle,
            "new_lifecycle": new_lifecycle,
            "intent": normalized_intent,
            "topic": topic,
            "decision": decision,
            "cta": cta,
            "repeat_count": repeat_count,
        },
    )
    return new_lifecycle, decision, cta


def create_policy_engine_node():
    """
    Factory function that creates a policy engine node.

    The policy engine is a pure Python function that uses lifecycle,
    extracted intent, dialog_state, and features to decide the next action.

    Returns:
        An async function that takes an AgentState dict and returns updates
        to the state (decision, lifecycle, cta, dialog_state, topic, lead_status).
    """
    async def _policy_engine_node_impl(state: AgentState) -> Dict[str, Any]:
        """
        Apply business rules to decide next action.

        Expected state fields:
          - lifecycle: Optional[str]
          - intent: Optional[str]
          - features: Optional[Dict]
          - user_memory: Optional[Dict]
          - dialog_state: Optional[Dict]

        Returns:
            Dict with decision, lifecycle (if changed), cta, dialog_state, topic, lead_status.
        """
        lifecycle = state.get("lifecycle") or DEFAULT_LIFECYCLE
        intent = state.get("intent")
        features = state.get("features")
        current_dialog_state = _extract_dialog_state(state)

        normalized_intent = _normalize_intent(intent)
        topic = _resolve_topic(normalized_intent, features)

        new_lifecycle, decision, cta = get_decision(
            lifecycle,
            normalized_intent,
            features=features,
            dialog_state=current_dialog_state,
        )

        next_dialog_state = _build_dialog_state_update(
            current_dialog_state,
            intent=normalized_intent,
            topic=topic,
            cta=cta,
            lifecycle=new_lifecycle,
            decision=decision,
            features=features,
        )

        logger.debug(
            "Policy decision finalized",
            extra={
                "old_lifecycle": lifecycle,
                "new_lifecycle": new_lifecycle,
                "intent": normalized_intent,
                "topic": topic,
                "decision": decision,
                "cta": cta,
                "repeat_count": next_dialog_state.get("repeat_count"),
                "lead_status": next_dialog_state.get("lead_status"),
            },
        )

        result = {
            "decision": decision,
            "cta": cta,
            "topic": topic,
            "lead_status": next_dialog_state.get("lead_status"),
            "dialog_state": next_dialog_state,
        }

        # Only include lifecycle if it changed.
        if new_lifecycle != lifecycle:
            result["lifecycle"] = new_lifecycle

        return result

    def _get_policy_input_size(state: AgentState) -> int:
        """
        Estimate policy node input size.

        Args:
            state: Current agent state.

        Returns:
            Rough input size in characters.
        """
        return (
            len(str(state.get("features") or "")) +
            len(str(state.get("intent") or "")) +
            len(str(state.get("dialog_state") or "")) +
            len(str((state.get("user_memory") or {}).get("dialog_state") or ""))
        )

    def _get_policy_output_size(result: Dict[str, Any]) -> int:
        """
        Estimate policy node output size.

        Args:
            result: Node result.

        Returns:
            Approximate size.
        """
        return len(str(result))

    async def policy_engine_node(state: AgentState) -> Dict[str, Any]:
        """
        Execute the policy engine with execution tracing.

        Args:
            state: Current agent state.

        Returns:
            Dictionary of state updates.
        """
        return await log_node_execution(
            "policy_engine",
            _policy_engine_node_impl,
            state,
            get_input_size=_get_policy_input_size,
            get_output_size=_get_policy_output_size,
        )

    return policy_engine_node
