"""
Rules-based routing node for LangGraph pipeline.

Applies cheap rules (no LLM) to determine the initial decision:
- If anger or refund keywords detected → ESCALATE
- If simple FAQ patterns matched → RESPOND with template answer
- If client profile missing → COLLECT_PROFILE
- Otherwise → PROCEED_TO_LLM (go to router)
"""

import re
from typing import Dict, Any

from src.core.logging import get_logger
from src.agent.state import AgentState

logger = get_logger(__name__)

# Simple keyword lists (can be extended or loaded from config)
ANGER_KEYWORDS = [
    "жрёт", "жрет", "тупит", "бесит", "развод", "мошенник", "недоволен",
    "верните деньги", "refund", "chargeback", "жалоба", "подавление",
    "невероятно дорого", "сжигаю контракт", "удалить аккаунт"
]

FAQ_PATTERNS = [
    (re.compile(r"доставк|delivery", re.IGNORECASE), "Доставка осуществляется в течение 1-3 рабочих дней."),
    (re.compile(r"цена|стоимост|price|cost", re.IGNORECASE), "Стоимость зависит от тарифа. Базовый пакет — 5000₽, поддержка от 1500₽/мес."),
    (re.compile(r"возврат|refund", re.IGNORECASE), "Возврат возможен в течение 14 дней при отсутствии выполненных работ. Обратитесь к менеджеру."),
    (re.compile(r"интеграц|integrat|crm|api", re.IGNORECASE), "Мы поддерживаем интеграцию через API, CSV и webhook. Для сложных случаев требуется участие менеджера.")
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


def _match_faq(text: str) -> tuple[bool, str]:
    """Check if text matches any FAQ pattern. Returns (matched, answer)."""
    for pattern, answer in FAQ_PATTERNS:
        if pattern.search(text):
            return True, answer
    return False, ""


async def rules_node(state: AgentState) -> Dict[str, Any]:
    """
    Apply cheap routing rules to the incoming state.

    Rules (executed in order):
      1. If anger detected -> decision = "ESCALATE", requires_human = True
      2. If FAQ pattern matched -> decision = "RESPOND", response_text = template answer
      3. If client_profile is None -> decision = "COLLECT_PROFILE"
      4. Otherwise -> decision = "PROCEED_TO_LLM"

    Returns a dictionary with updates to the state (decision, response_text, requires_human).

    Args:
        state: Current AgentState (must contain user_input and client_profile).

    Returns:
        Dict with keys to update in the state.
    """
    user_input = state.get("user_input", "")
    client_profile = state.get("client_profile")

    if not user_input:
        logger.warning("rules_node called with empty user_input")
        return {"decision": "PROCEED_TO_LLM"}

    # Rule 1: anger detection
    if _detect_anger(user_input):
        logger.info("Rule triggered: anger detected -> ESCALATE")
        return {
            "decision": "ESCALATE",
            "requires_human": True,
            "response_text": "Извините за неудобства. Я передал ваш запрос менеджеру, он свяжется с вами в ближайшее время."
        }

    # Rule 2: FAQ match
    matched, answer = _match_faq(user_input)
    if matched:
        logger.debug("Rule triggered: FAQ match -> RESPOND")
        return {
            "decision": "RESPOND",
            "response_text": answer,
            "requires_human": False
        }

    # Rule 3: missing client profile
    if client_profile is None:
        logger.debug("Rule triggered: missing client profile -> COLLECT_PROFILE")
        return {"decision": "COLLECT_PROFILE"}

    # Default: proceed to LLM router
    logger.debug("No rule triggered, proceeding to LLM")
    return {"decision": "PROCEED_TO_LLM"}
