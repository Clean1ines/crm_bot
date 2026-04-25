from typing import Any

from src.domain.runtime.dialog_state import default_dialog_state
from .lifecycle import DEFAULT_LIFECYCLE

REPEAT_SOFT_THRESHOLD = 2
REPEAT_ESCALATION_THRESHOLD = 3


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def calculate_repeat_count(previous_dialog_state: dict[str, Any], intent: str, topic: str) -> int:
    prev_intent = str(previous_dialog_state.get("last_intent") or "").strip().lower()
    prev_topic = str(previous_dialog_state.get("last_topic") or "").strip().lower()
    previous_count = _coerce_int(previous_dialog_state.get("repeat_count"), 0)

    if not intent:
        return previous_count

    if intent == prev_intent or topic == prev_topic:
        return previous_count + 1

    return 1


def build_dialog_state_update(
    previous_dialog_state: dict[str, Any],
    *,
    intent: str,
    topic: str,
    cta: str,
    lifecycle: str,
    decision: str,
    features: dict[str, Any] | None = None,
) -> dict[str, Any]:
    dialog_state = default_dialog_state(lifecycle=lifecycle)
    dialog_state.update(previous_dialog_state or {})

    repeat_count = calculate_repeat_count(previous_dialog_state, intent, topic)
    dialog_state["repeat_count"] = repeat_count

    if intent:
        dialog_state["last_intent"] = intent

    if topic:
        dialog_state["last_topic"] = topic

    if cta and cta != "none":
        dialog_state["last_cta"] = cta

    lead_status = str(dialog_state.get("lead_status") or lifecycle or DEFAULT_LIFECYCLE).strip().lower()
    if lead_status == "hot":
        lead_status = "warm"

    if lifecycle in {"handoff_to_manager", "angry"} or decision == "ESCALATE_TO_HUMAN":
        lead_status = "handoff_to_manager"
    elif lifecycle == "active_client":
        lead_status = "active_client"
    elif cta == "call_manager":
        lead_status = "handoff_to_manager"
    elif cta == "book_consultation":
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
