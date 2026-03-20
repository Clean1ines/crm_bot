"""
Intent extraction node for LangGraph pipeline.

Uses a lightweight LLM to detect user intent, call-to-action, and mentioned features.
"""

import json
from typing import Dict, Any, Optional

from langchain_groq import ChatGroq

from src.core.config import settings
from src.core.logging import get_logger, log_node_execution
from src.agent.state import AgentState
from src.agent.schemas import IntentOutput
from src.agent.router.prompt_builder import build_intent_prompt

logger = get_logger(__name__)


def create_intent_extractor_node(
    llm: Optional[ChatGroq] = None,
    model_name: str = "llama-3.1-8b-instant"
):
    """
    Factory function that creates an intent extraction node.

    Args:
        llm: Optional pre-configured ChatGroq instance. If None, creates one.
        model_name: Model name to use for extraction (default: lightweight).

    Returns:
        An async function that takes an AgentState dict and returns a dict
        with updates to the state (intent, cta, features, topic, emotion, is_repeat_like).
    """
    if llm is None:
        llm = ChatGroq(
            model=model_name,
            temperature=0.0,
            max_tokens=150,
            api_key=settings.GROQ_API_KEY,
        )

    async def _intent_extractor_node_impl(state: AgentState) -> Dict[str, Any]:
        """
        Extract intent, call-to-action, and features from user input.

        Expected state fields:
          - user_input: str
          - conversation_summary: Optional[str]
          - history: Optional[List[Dict]]
          - user_memory: Optional[Dict]

        Actions:
          1. Build prompt using build_intent_prompt.
          2. Call lightweight LLM.
          3. Parse JSON response into IntentOutput.
          4. Return intent, cta, features, topic, emotion, is_repeat_like.

        Returns:
            Dict with intent, cta, features, topic, cta_hint, emotion, is_repeat_like.
        """
        user_input = state.get("user_input", "")
        if not user_input:
            logger.debug("No user_input, skipping intent extraction")
            return {}

        # Build prompt
        prompt = build_intent_prompt(
            user_input=user_input,
            conversation_summary=state.get("conversation_summary"),
            history=state.get("history"),
            user_memory=state.get("user_memory")
        )

        try:
            response = await llm.ainvoke([("human", prompt)])
            content = response.content.strip()

            # Parse JSON
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            data = json.loads(content)

            # Validate using Pydantic
            intent_data = IntentOutput(**data)

            logger.debug(
                "Intent extracted",
                extra={
                    "intent": intent_data.intent,
                    "cta": intent_data.cta,
                    "topic": intent_data.topic,
                    "emotion": intent_data.emotion,
                    "is_repeat_like": intent_data.is_repeat_like,
                    "features": intent_data.features
                }
            )
            return {
                "intent": intent_data.intent,
                "cta": intent_data.cta,
                "features": intent_data.features,
                "topic": intent_data.topic,
                "cta_hint": intent_data.cta_hint,
                "emotion": intent_data.emotion,
                "is_repeat_like": intent_data.is_repeat_like
            }

        except Exception as e:
            logger.warning(
                "Intent extraction failed",
                extra={"error": str(e), "user_input": user_input[:100]}
            )
            return {}  # fallback, no updates

    def _get_intent_input_size(state: AgentState) -> int:
        # Safely compute lengths, treating None as empty string
        return (
            len(state.get("user_input") or "") +
            len(state.get("conversation_summary") or "") +
            len(str(state.get("history") or [])) +
            len(str(state.get("user_memory") or {}))
        )

    def _get_intent_output_size(result: Dict[str, Any]) -> int:
        return len(str(result))

    async def intent_extractor_node(state: AgentState) -> Dict[str, Any]:
        return await log_node_execution(
            "intent_extractor",
            _intent_extractor_node_impl,
            state,
            get_input_size=_get_intent_input_size,
            get_output_size=_get_intent_output_size
        )

    return intent_extractor_node
