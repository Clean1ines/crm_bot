"""
Response generator node for the LangGraph pipeline.

Uses the configured LLM to craft the final answer from decision, history,
knowledge, memory, and project runtime configuration.
"""

from typing import Any

from langchain_groq import ChatGroq

from src.agent.router.prompt_builder import build_response_prompt
from src.agent.state import AgentState
from src.domain.runtime.project_runtime_profile import ProjectRuntimeProfile
from src.domain.runtime.response_generation import (
    ResponseGenerationContext,
    ResponseGenerationResult,
)
from src.infrastructure.config.settings import settings
from src.infrastructure.logging.logger import get_logger, log_node_execution

logger = get_logger(__name__)


def _merge_dialog_state_into_user_memory(
    user_memory: dict[str, list[dict[str, Any]]] | None,
    dialog_state: dict[str, Any] | None,
) -> dict[str, list[dict[str, Any]]] | None:
    if not dialog_state:
        return user_memory

    merged: dict[str, list[dict[str, Any]]] = {}
    if user_memory:
        for memory_type, items in user_memory.items():
            normalized_items: list[dict[str, Any]] = []
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict):
                        normalized_items.append(dict(item))
                    else:
                        normalized_items.append({"key": "value", "value": item})
            merged[memory_type] = normalized_items

    merged["dialog_state"] = [{"key": "dialog_state", "value": dialog_state}]
    return merged


def _resolve_response_model_name(state: AgentState, default_model: str) -> str:
    profile = ProjectRuntimeProfile.from_configuration(state.get("project_configuration"))
    return profile.fallback_model or default_model


def create_response_generator_node(
    llm: ChatGroq | None = None,
    model_name: str | None = None,
):
    """
    Create the response-generator graph node.

    Args:
        llm: Optional pre-configured base LLM client.
        model_name: Optional base model override.

    Returns:
        Async LangGraph node that emits a response_text state patch.
    """

    base_model = model_name or settings.GROQ_MODEL
    if llm is None:
        llm = ChatGroq(
            model=base_model,
            temperature=0.3,
            max_tokens=500,
            api_key=settings.GROQ_API_KEY,
        )

    async def _response_generator_node_impl(state: AgentState) -> dict[str, Any]:
        context = ResponseGenerationContext.from_state(state)
        if context.decision not in {"LLM_GENERATE", "RESPOND_KB", "RESPOND_TEMPLATE"}:
            logger.debug(
                "Skipping response generation, decision not generative",
                extra={"decision": context.decision},
            )
            return {}

        merged_memory = _merge_dialog_state_into_user_memory(
            context.user_memory,
            context.dialog_state,
        )
        logger.debug(
            "Preparing response prompt",
            extra={
                "decision": context.decision,
                "history_count": len(context.history),
                "knowledge_chunk_count": len(context.knowledge_chunks),
                "has_dialog_state": bool(context.dialog_state),
            },
        )

        prompt = build_response_prompt(
            decision=context.decision,
            user_input=context.user_input,
            conversation_summary=context.conversation_summary,
            history=context.history,
            knowledge_chunks=context.knowledge_chunks,
            user_memory=merged_memory,
            features=context.features,
            project_configuration=context.project_configuration,
        )

        try:
            selected_model = _resolve_response_model_name(state, base_model)
            llm_for_request = llm
            if selected_model != base_model:
                llm_for_request = ChatGroq(
                    model=selected_model,
                    temperature=0.3,
                    max_tokens=500,
                    api_key=settings.GROQ_API_KEY,
                )

            response = await llm_for_request.ainvoke([("human", prompt)])
            response_text = (response.content or "").strip()

            metadata: dict[str, Any] = {}

            logger.debug(
                "Response generated",
                extra={
                    "response_length": len(response_text),
                    "decision": context.decision,
                    "model": selected_model,
                },
            )
            return ResponseGenerationResult(
                response_text=response_text,
                metadata=metadata,
            ).to_state_patch()
        except Exception as exc:
            logger.exception(
                "Response generation failed",
                extra={
                    "decision": context.decision,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "policy": "fallback_user_visible_error",
                },
            )
            return ResponseGenerationResult(
                response_text="Sorry, something went wrong while generating the response. Please try again later.",
            ).to_state_patch()

    def _get_response_input_size(state: AgentState) -> int:
        context = ResponseGenerationContext.from_state(state)
        return (
            len(context.user_input)
            + len(context.conversation_summary or "")
            + len(str(context.history))
            + len(str(context.knowledge_chunks))
            + len(str(context.user_memory or {}))
            + len(str(context.project_configuration or {}))
            + len(str(context.dialog_state or {}))
        )

    def _get_response_output_size(result: dict[str, Any]) -> int:
        return len(result.get("response_text", ""))

    async def response_generator_node(state: AgentState) -> dict[str, Any]:
        return await log_node_execution(
            "response_generator",
            _response_generator_node_impl,
            state,
            get_input_size=_get_response_input_size,
            get_output_size=_get_response_output_size,
        )

    return response_generator_node
