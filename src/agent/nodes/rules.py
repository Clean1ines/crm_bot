"""
Rules-based routing node for the LangGraph pipeline.

Applies cheap rules before LLM work:
- resolve pending handoff confirmations;
- ask for handoff confirmation on obvious anger signals;
- otherwise continue into the regular LLM pipeline.
"""

from src.agent.state import AgentState
from src.domain.runtime.dialog_state import merge_dialog_state
from src.domain.runtime.policy.handoff_confirmation import (
    build_handoff_confirmation_text,
    build_handoff_details_requested_text,
    clear_handoff_confirmation,
    is_handoff_confirmation_pending,
    resolve_handoff_confirmation_reply,
    with_handoff_confirmation_pending,
)
from src.infrastructure.logging.logger import get_logger, log_node_execution

logger = get_logger(__name__)

ANGER_KEYWORDS = [
    "\u0436\u0440\u0451\u0442",
    "\u0436\u0440\u0435\u0442",
    "\u0442\u0443\u043f\u0438\u0442",
    "\u0431\u0435\u0441\u0438\u0442",
    "\u0440\u0430\u0437\u0432\u043e\u0434",
    "\u043c\u043e\u0448\u0435\u043d\u043d\u0438\u043a",
    "\u043d\u0435\u0434\u043e\u0432\u043e\u043b\u0435\u043d",
    "\u0432\u0435\u0440\u043d\u0438\u0442\u0435 \u0434\u0435\u043d\u044c\u0433\u0438",
    "refund",
    "chargeback",
    "\u0436\u0430\u043b\u043e\u0431\u0430",
    "\u043f\u043e\u0434\u0430\u0432\u043b\u0435\u043d\u0438\u0435",
    "\u043d\u0435\u0432\u0435\u0440\u043e\u044f\u0442\u043d\u043e \u0434\u043e\u0440\u043e\u0433\u043e",
    "\u0441\u0436\u0438\u0433\u0430\u044e \u043a\u043e\u043d\u0442\u0440\u0430\u043a\u0442",
    "\u0443\u0434\u0430\u043b\u0438\u0442\u044c \u0430\u043a\u043a\u0430\u0443\u043d\u0442",
]

CAPS_THRESHOLD = 0.5


def _detect_anger(text: str) -> bool:
    text_lower = text.lower()
    for keyword in ANGER_KEYWORDS:
        if keyword in text_lower:
            logger.debug("Anger keyword matched", extra={"keyword": keyword})
            return True

    letters = [character for character in text if character.isalpha()]
    if not letters:
        return False

    caps_ratio = sum(1 for character in letters if character.isupper()) / len(letters)
    if caps_ratio > CAPS_THRESHOLD:
        logger.debug("High caps ratio detected", extra={"ratio": caps_ratio})
        return True

    return False


async def _rules_node_impl(state: AgentState) -> dict[str, object]:
    user_input = str(state.get("user_input") or "")
    if not user_input:
        logger.warning("rules_node called with empty user_input")
        return {"decision": "PROCEED_TO_LLM"}

    dialog_state = merge_dialog_state(state.get("dialog_state"))
    if is_handoff_confirmation_pending(dialog_state):
        confirmation_reply = resolve_handoff_confirmation_reply(user_input)
        cleared_dialog_state = clear_handoff_confirmation(dialog_state)

        if confirmation_reply == "confirm":
            logger.info("Rule triggered: handoff confirmation accepted")
            return {
                "decision": "ESCALATE",
                "dialog_state": cleared_dialog_state,
            }

        if confirmation_reply == "decline":
            logger.info("Rule triggered: handoff confirmation declined")
            return {
                "decision": "RESPOND",
                "response_text": build_handoff_details_requested_text(),
                "requires_human": False,
                "dialog_state": cleared_dialog_state,
            }

        logger.info("Rule triggered: handoff confirmation replaced by new details")
        return {
            "decision": "PROCEED_TO_LLM",
            "dialog_state": cleared_dialog_state,
        }

    if _detect_anger(user_input):
        logger.info("Rule triggered: anger detected -> request handoff confirmation")
        return {
            "decision": "RESPOND",
            "requires_human": False,
            "response_text": build_handoff_confirmation_text(user_input),
            "dialog_state": with_handoff_confirmation_pending(dialog_state),
        }

    logger.debug("No rule triggered, proceeding to LLM pipeline")
    return {"decision": "PROCEED_TO_LLM"}


def _get_rules_input_size(state: AgentState) -> int:
    return len(str(state.get("user_input") or ""))


def _get_rules_output_size(result: dict[str, object]) -> int:
    return 1


async def rules_node(state: AgentState) -> dict[str, object]:
    return await log_node_execution(
        "rules",
        _rules_node_impl,
        state,
        get_input_size=_get_rules_input_size,
        get_output_size=_get_rules_output_size,
    )
