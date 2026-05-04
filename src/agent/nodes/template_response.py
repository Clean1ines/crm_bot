"""
Template response node.

Handles deterministic responses that must not call KB/RAG or response LLM:
- greetings,
- out-of-domain requests,
- ambiguous short turns,
- technical failures already converted to user-visible text.
"""

from src.agent.state import AgentState
from src.infrastructure.logging.logger import get_logger, log_node_execution

logger = get_logger(__name__)

GREETING_TEXT = (
    "Здравствуйте. Я могу помочь с вопросами о сервисе, стоимости, возможностях, "
    "интеграциях, подключении и передаче диалога менеджеру. Напишите, что хотите уточнить."
)

OUT_OF_DOMAIN_TEXT = (
    "Я помогаю с вопросами по сервису, автоматизации клиентских ответов, интеграциям, "
    "стоимости, подключению и передаче диалога менеджеру. Переформулируйте вопрос по этим темам "
    "или напишите «позвать менеджера»."
)

AMBIGUOUS_TEXT = (
    "Не до конца понял, к какому вопросу это относится. Напишите вопрос подробнее "
    "или скажите «позвать менеджера»."
)

GENERIC_TEXT = (
    "Напишите вопрос по сервису, стоимости, интеграциям или подключению. "
    "Также можно попросить позвать менеджера."
)


def _template_text(state: AgentState) -> str:
    existing = state.get("response_text")
    if existing:
        return str(existing)

    domain = str(state.get("domain") or "").strip().lower()
    turn_relation = str(state.get("turn_relation") or "").strip().lower()

    if domain == "technical_failure":
        return GENERIC_TEXT
    if domain == "greeting":
        return GREETING_TEXT
    if domain == "out_of_domain":
        return OUT_OF_DOMAIN_TEXT
    if domain == "ambiguous" or turn_relation == "short_reply":
        return AMBIGUOUS_TEXT

    return GENERIC_TEXT


async def _template_response_node_impl(state: AgentState) -> dict[str, object]:
    text = _template_text(state)
    logger.debug(
        "Template response selected",
        extra={
            "domain": state.get("domain"),
            "turn_relation": state.get("turn_relation"),
            "response_preview": text[:80],
        },
    )
    return {
        "decision": "RESPOND",
        "response_text": text,
        "requires_human": False,
        "should_search_kb": False,
        "should_generate_answer": False,
    }


async def template_response_node(state: AgentState) -> dict[str, object]:
    return await log_node_execution(
        "template_response",
        _template_response_node_impl,
        state,
    )
