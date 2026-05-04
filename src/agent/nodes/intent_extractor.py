"""
Intent extraction node for LangGraph pipeline.

Uses a lightweight LLM to extract domain, intent, CTA, topic, emotion, and feature hints.
"""

import json
from typing import Protocol, cast

from src.agent.router.prompt_builder import build_intent_prompt
from src.agent.state import AgentState
from src.domain.runtime.intent_extraction import (
    IntentExtractionContext,
    IntentExtractionResult,
)
from src.domain.runtime.state_contracts import RuntimeStateInput
from src.infrastructure.config.settings import settings
from src.infrastructure.logging.logger import get_logger, log_node_execution

logger = get_logger(__name__)

TECHNICAL_CLASSIFICATION_FIRST_TEXT = (
    "Не получилось обработать запрос из-за технической ошибки. "
    "Можете повторить запрос, а если вопрос срочный — я передам диалог менеджеру."
)

TECHNICAL_CLASSIFICATION_REPEAT_TEXT = (
    "Техническая ошибка повторилась. Я уже передал технический инцидент владельцу проекта. "
    "Можете позвать менеджера, чтобы не ждать восстановления ассистента."
)


class ChatMessageResponse(Protocol):
    content: str | None


class ChatGroqClient(Protocol):
    async def ainvoke(self, messages: list[tuple[str, str]]) -> ChatMessageResponse: ...


class ChatGroqFactory(Protocol):
    def __call__(
        self,
        *,
        model: str,
        temperature: float,
        max_tokens: int,
        api_key: object,
    ) -> ChatGroqClient: ...


ChatGroq: ChatGroqFactory | None = None


def _chat_groq_class() -> ChatGroqFactory:
    if ChatGroq is not None:
        return ChatGroq

    from langchain_groq import ChatGroq as ImportedChatGroq

    return cast(ChatGroqFactory, ImportedChatGroq)


def _prompt_memory_from_runtime(
    value: object,
) -> dict[str, list[dict[str, object]]] | None:
    if not isinstance(value, dict):
        return None

    normalized: dict[str, list[dict[str, object]]] = {}
    for key, raw_items in value.items():
        if not isinstance(raw_items, list):
            continue

        items: list[dict[str, object]] = []
        for item in raw_items:
            if isinstance(item, dict):
                items.append(
                    {str(item_key): item_value for item_key, item_value in item.items()}
                )

        normalized[str(key)] = items

    return normalized or None


def _unwrap_json_block(content: str) -> str:
    text = content.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return text.strip()


def _coerce_int(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return default
    return default


def _technical_failure_patch(state: AgentState, exc: Exception) -> dict[str, object]:
    previous_count = _coerce_int(state.get("technical_failure_count"), 0)
    next_count = previous_count + 1
    return {
        "decision": "RESPOND",
        "response_text": (
            TECHNICAL_CLASSIFICATION_REPEAT_TEXT
            if next_count >= 2
            else TECHNICAL_CLASSIFICATION_FIRST_TEXT
        ),
        "requires_human": False,
        "domain": "technical_failure",
        "turn_relation": "unknown",
        "should_search_kb": False,
        "should_generate_answer": False,
        "should_offer_manager": True,
        "technical_failure_count": next_count,
        "technical_failure_stage": "intent_extractor",
        "technical_failure_error": type(exc).__name__,
        "technical_incident_created": bool(
            state.get("technical_incident_created") or False
        ),
    }


def create_intent_extractor_node(
    llm: ChatGroqClient | None = None,
    model_name: str = "llama-3.1-8b-instant",
):
    """
    Create the intent-extractor node with an optional lightweight LLM client.
    """

    if llm is None:
        llm = _chat_groq_class()(
            model=model_name,
            temperature=0.0,
            max_tokens=220,
            api_key=settings.GROQ_API_KEY,
        )

    async def _intent_extractor_node_impl(state: AgentState) -> dict[str, object]:
        context = IntentExtractionContext.from_state(cast(RuntimeStateInput, state))
        if not context.user_input:
            logger.debug("No user_input, skipping intent extraction")
            return {}

        prompt = build_intent_prompt(
            user_input=context.user_input,
            conversation_summary=context.conversation_summary,
            history=context.history,
            user_memory=_prompt_memory_from_runtime(context.user_memory),
        )

        try:
            response = await llm.ainvoke([("human", prompt)])
            payload = json.loads(_unwrap_json_block(str(response.content or "")))
            result = IntentExtractionResult.from_llm_payload(
                payload
            ).normalized_for_context(context)
            logger.debug(
                "Intent extracted",
                extra={
                    "domain": result.domain,
                    "turn_relation": result.turn_relation,
                    "intent": result.intent,
                    "cta": result.cta,
                    "topic": result.topic,
                    "emotion": result.emotion,
                    "is_repeat_like": result.is_repeat_like,
                    "features": result.features,
                    "should_search_kb": result.should_search_kb,
                    "should_generate_answer": result.should_generate_answer,
                    "should_offer_manager": result.should_offer_manager,
                },
            )
            return dict(result.to_state_patch())
        except Exception as exc:
            logger.warning(
                "Intent extraction failed",
                extra={
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "user_input": context.user_input[:100],
                    "policy": "technical_failure_user_choice",
                },
            )
            return _technical_failure_patch(state, exc)

    def _get_intent_input_size(state: AgentState) -> int:
        context = IntentExtractionContext.from_state(cast(RuntimeStateInput, state))
        return (
            len(context.user_input)
            + len(context.conversation_summary or "")
            + len(str(context.history))
            + len(str(context.user_memory or {}))
        )

    def _get_intent_output_size(result: dict[str, object]) -> int:
        return len(str(result))

    async def intent_extractor_node(state: AgentState) -> dict[str, object]:
        return await log_node_execution(
            "intent_extractor",
            _intent_extractor_node_impl,
            state,
            get_input_size=_get_intent_input_size,
            get_output_size=_get_intent_output_size,
        )

    return intent_extractor_node
