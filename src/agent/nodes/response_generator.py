"""
Response generator node for LangGraph pipeline.

Uses a powerful LLM to craft final answer based on decision, context, and memory.
"""

import asyncio
from typing import Dict, Any, Optional

from langchain_groq import ChatGroq

from src.core.config import settings
from src.core.logging import get_logger, log_node_execution
from src.agent.state import AgentState
from src.agent.router.prompt_builder import build_response_prompt

logger = get_logger(__name__)


def create_response_generator_node(
    llm: Optional[ChatGroq] = None,
    model_name: Optional[str] = None
):
    """
    Factory function that creates a response generator node.

    Args:
        llm: Optional pre-configured ChatGroq instance. If None, creates one using settings.
        model_name: Optional model name (defaults to settings.GROQ_MODEL).

    Returns:
        An async function that takes an AgentState dict and returns a dict
        with updates to the state (response_text).
    """
    if llm is None:
        model = model_name or settings.GROQ_MODEL
        llm = ChatGroq(
            model=model,
            temperature=0.3,
            max_tokens=500,
            api_key=settings.GROQ_API_KEY,
        )

    async def _response_generator_node_impl(state: AgentState) -> Dict[str, Any]:
        """
        Generate final response using LLM.

        Expected state fields:
          - decision: str (e.g., "LLM_GENERATE")
          - user_input: str
          - conversation_summary: Optional[str]
          - history: Optional[List[Dict]]
          - knowledge_chunks: Optional[List[Dict]]
          - user_memory: Optional[Dict]
          - features: Optional[Dict] (may be used)
          - cta: Optional[str] (may be used)

        Actions:
          1. Build prompt using build_response_prompt.
          2. Call LLM to generate final answer.
          3. Store response_text in state.

        Returns:
            Dict with response_text.
        """
        # Skip if decision indicates we should not generate (e.g., tool call)
        decision = state.get("decision", "LLM_GENERATE")
        if decision not in ["LLM_GENERATE", "RESPOND_KB", "RESPOND_TEMPLATE"]:
            logger.debug("Skipping response generation, decision not generative", extra={"decision": decision})
            return {}

        # Build prompt
        prompt = build_response_prompt(
            user_input=state.get("user_input", ""),
            conversation_summary=state.get("conversation_summary"),
            history=state.get("history"),
            knowledge_chunks=state.get("knowledge_chunks"),
            user_memory=state.get("user_memory"),
            features=state.get("features"),
            cta=state.get("cta")
        )

        try:
            response = await llm.ainvoke([("human", prompt)])
            response_text = response.content.strip()

            logger.debug(
                "Response generated",
                extra={
                    "response_length": len(response_text),
                    "decision": decision
                }
            )
            return {"response_text": response_text}

        except Exception as e:
            logger.exception("Response generation failed", extra={"decision": decision})
            return {
                "response_text": "Извините, произошла ошибка при формировании ответа. Попробуйте позже."
            }

    def _get_response_input_size(state: AgentState) -> int:
        return (
            len(state.get("user_input", "")) +
            len(state.get("conversation_summary", "")) +
            len(str(state.get("history", []))) +
            len(str(state.get("knowledge_chunks", []))) +
            len(str(state.get("user_memory", {})))
        )

    def _get_response_output_size(result: Dict[str, Any]) -> int:
        return len(result.get("response_text", ""))

    async def response_generator_node(state: AgentState) -> Dict[str, Any]:
        return await log_node_execution(
            "response_generator",
            _response_generator_node_impl,
            state,
            get_input_size=_get_response_input_size,
            get_output_size=_get_response_output_size
        )

    return response_generator_node
