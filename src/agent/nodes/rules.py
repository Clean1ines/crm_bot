"""
Rules-based routing node for LangGraph pipeline.

Applies cheap rules (no LLM) to determine the initial decision:
- If anger detected → ESCALATE
- Otherwise → PROCEED_TO_LLM
"""

import re

from src.infrastructure.logging.logger import get_logger, log_node_execution
from src.agent.state import AgentState

logger = get_logger(__name__)

# Simple keyword list (can be extended or loaded from config)
ANGER_KEYWORDS = [
    "жрёт", "жрет", "тупит", "бесит", "развод", "мошенник", "недоволен",
    "верните деньги", "refund", "chargeback", "жалоба", "подавление",
    "невероятно дорого", "сжигаю контракт", "удалить аккаунт"
]

# Threshold for detecting anger via caps proportion
CAPS_THRESHOLD = 0.5  # if more than 50% of letters are uppercase -> anger


def _detect_anger(text: str) -> bool:
    """Detect anger based on keywords and excessive caps."""
    text_lower = text.lower()
    for kw in ANGER_KEYWORDS:
        if kw in text_lower:
            logger.debug("Anger keyword matched", extra={"keyword": kw})
            return True

    # Count uppercase letters (excluding non-letters)
    letters = [ch for ch in text if ch.isalpha()]
    if letters:
        caps_ratio = sum(1 for ch in letters if ch.isupper()) / len(letters)
        if caps_ratio > CAPS_THRESHOLD:
            logger.debug("High caps ratio detected", extra={"ratio": caps_ratio})
            return True

    return False


async def _rules_node_impl(state: AgentState) -> dict[str, object]:
    """
    Apply cheap routing rules to the incoming state.

    Rules (executed in order):
      1. If anger detected -> decision = "ESCALATE", requires_human = True
      2. Otherwise -> decision = "PROCEED_TO_LLM"

    Returns a dictionary with updates to the state (decision, response_text, requires_human).

    Args:
        state: Current AgentState (must contain user_input and client_profile).

    Returns:
        Dict with keys to update in the state.
    """
    user_input = state.get("user_input", "")

    if not user_input:
        logger.warning("rules_node called with empty user_input")
        return {"decision": "PROCEED_TO_LLM"}

    # Anger detection
    if _detect_anger(user_input):
        logger.info("Rule triggered: anger detected -> ESCALATE")
        return {
            "decision": "ESCALATE",
            "requires_human": True,
            "response_text": "Извините за неудобства. Я передал ваш запрос менеджеру, он свяжется с вами в ближайшее время."
        }

    # Default: proceed to LLM processing (kb_search -> intent_extractor)
    logger.debug("No rule triggered, proceeding to LLM pipeline")
    return {"decision": "PROCEED_TO_LLM"}


def _get_rules_input_size(state: AgentState) -> int:
    return len(state.get("user_input", ""))

def _get_rules_output_size(result: dict[str, object]) -> int:
    # output is a small decision dict, we can return 1 as approximation
    return 1

async def rules_node(state: AgentState) -> dict[str, object]:
    return await log_node_execution(
        "rules",
        _rules_node_impl,
        state,
        get_input_size=_get_rules_input_size,
        get_output_size=_get_rules_output_size
    )
