"""
Intent extraction node for LangGraph pipeline.

Uses a lightweight LLM to extract intent, CTA, topic, emotion, and feature hints.
"""

import json
from typing import Any

from langchain_groq import ChatGroq

from src.agent.router.prompt_builder import build_intent_prompt
from src.agent.state import AgentState
from src.domain.runtime.intent_extraction import (
    IntentExtractionContext,
    IntentExtractionResult,
)
from src.infrastructure.config.settings import settings
from src.infrastructure.logging.logger import get_logger, log_node_execution

logger = get_logger(__name__)


def _unwrap_json_block(content: str) -> str:
    text = content.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return text.strip()


def create_intent_extractor_node(
    llm: ChatGroq | None = None,
    model_name: str = "llama-3.1-8b-instant",
):
    """
    Create the intent-extractor node with an optional lightweight LLM client.
    """

    if llm is None:
        llm = ChatGroq(
            model=model_name,
            temperature=0.0,
            max_tokens=150,
            api_key=settings.GROQ_API_KEY,
        )

    async def _intent_extractor_node_impl(state: AgentState) -> dict[str, Any]:
        context = IntentExtractionContext.from_state(state)
        if not context.user_input:
            logger.debug("No user_input, skipping intent extraction")
            return {}

        prompt = build_intent_prompt(
            user_input=context.user_input,
            conversation_summary=context.conversation_summary,
            history=context.history,
            user_memory=context.user_memory,
        )

        try:
            response = await llm.ainvoke([("human", prompt)])
            payload = json.loads(_unwrap_json_block(str(response.content or "")))
            result = IntentExtractionResult.from_llm_payload(payload)
            logger.debug(
                "Intent extracted",
                extra={
                    "intent": result.intent,
                    "cta": result.cta,
                    "topic": result.topic,
                    "emotion": result.emotion,
                    "is_repeat_like": result.is_repeat_like,
                    "features": result.features,
                },
            )
            return result.to_state_patch()
        except Exception as exc:
            logger.warning(
                "Intent extraction failed",
                extra={"error": str(exc), "user_input": context.user_input[:100]},
            )
            return {}

    def _get_intent_input_size(state: AgentState) -> int:
        context = IntentExtractionContext.from_state(state)
        return (
            len(context.user_input)
            + len(context.conversation_summary or "")
            + len(str(context.history))
            + len(str(context.user_memory or {}))
        )

    def _get_intent_output_size(result: dict[str, Any]) -> int:
        return len(str(result))

    async def intent_extractor_node(state: AgentState) -> dict[str, Any]:
        return await log_node_execution(
            "intent_extractor",
            _intent_extractor_node_impl,
            state,
            get_input_size=_get_intent_input_size,
            get_output_size=_get_intent_output_size,
        )

    return intent_extractor_node
