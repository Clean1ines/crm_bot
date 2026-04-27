"""
Response generator node for the LangGraph pipeline.

Uses the configured LLM to craft the final answer from decision, history,
knowledge, memory, and project runtime configuration.
"""

from collections.abc import Mapping
from typing import cast
from langchain_groq import ChatGroq

from src.agent.router.prompt_builder import build_response_prompt
from src.agent.state import AgentState
from src.domain.runtime.state_contracts import RuntimeHistoryMessage, RuntimeStateInput
from src.domain.runtime.project_runtime_profile import ProjectRuntimeProfile
from src.domain.runtime.response_generation import (
    ResponseGenerationContext,
    ResponseGenerationResult,
)
from src.infrastructure.config.settings import settings
from src.infrastructure.logging.logger import get_logger, log_node_execution

logger = get_logger(__name__)


def _merge_dialog_state_into_user_memory(
    user_memory: dict[str, list[dict[str, object]]] | None,
    dialog_state: dict[str, object] | None,
) -> dict[str, list[dict[str, object]]] | None:
    if not dialog_state:
        return user_memory

    merged: dict[str, list[dict[str, object]]] = {}
    if user_memory:
        for memory_type, items in user_memory.items():
            merged[memory_type] = [dict(item) for item in items]

    merged["dialog_state"] = [{"key": "dialog_state", "value": dialog_state}]
    return merged


def _resolve_response_model_name(state: AgentState, default_model: str) -> str:
    profile = ProjectRuntimeProfile.from_configuration(
        state.get("project_configuration")
    )
    return profile.fallback_model or default_model


def _prompt_user_memory(value: object) -> dict[str, list[dict[str, object]]] | None:
    if not isinstance(value, Mapping):
        return None

    normalized: dict[str, list[dict[str, object]]] = {}
    for raw_key, raw_items in value.items():
        if not isinstance(raw_key, str) or not isinstance(raw_items, list):
            continue

        items: list[dict[str, object]] = []
        for raw_item in raw_items:
            if isinstance(raw_item, Mapping):
                items.append(
                    {
                        str(item_key): item_value
                        for item_key, item_value in raw_item.items()
                    }
                )

        normalized[raw_key] = items

    return normalized


def _prompt_dialog_state(value: object) -> dict[str, object] | None:
    if not isinstance(value, Mapping):
        return None
    return {str(key): item for key, item in value.items()}


def _prompt_history(value: object) -> list[RuntimeHistoryMessage] | None:
    if not isinstance(value, list):
        return None

    history: list[RuntimeHistoryMessage] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue

        role = item.get("role")
        content = item.get("content")
        if role is None or content is None:
            continue

        history.append(
            RuntimeHistoryMessage(
                role=str(role),
                content=str(content),
            )
        )

    return history


def _prompt_features(value: object) -> dict[str, float] | None:
    if not isinstance(value, Mapping):
        return None

    features: dict[str, float] = {}
    for key, raw_value in value.items():
        if not isinstance(key, str):
            continue
        try:
            features[key] = float(raw_value)
        except (TypeError, ValueError):
            continue

    return features


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

    async def _response_generator_node_impl(state: AgentState) -> dict[str, object]:
        context = ResponseGenerationContext.from_state(cast(RuntimeStateInput, state))
        if context.decision not in {"LLM_GENERATE", "RESPOND_KB", "RESPOND_TEMPLATE"}:
            logger.debug(
                "Skipping response generation, decision not generative",
                extra={"decision": context.decision},
            )
            return {}

        merged_memory = _merge_dialog_state_into_user_memory(
            _prompt_user_memory(context.user_memory),
            _prompt_dialog_state(context.dialog_state),
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
            history=_prompt_history(context.history),
            knowledge_chunks=context.knowledge_chunks,
            user_memory=merged_memory,
            features=_prompt_features(context.features),
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

            metadata: dict[str, object] = {}

            logger.debug(
                "Response generated",
                extra={
                    "response_length": len(response_text),
                    "decision": context.decision,
                    "model": selected_model,
                },
            )
            return dict(
                ResponseGenerationResult(
                    response_text=response_text,
                    metadata=metadata,
                ).to_state_patch()
            )
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
            return dict(
                ResponseGenerationResult(
                    response_text="Sorry, something went wrong while generating the response. Please try again later.",
                ).to_state_patch()
            )

    def _get_response_input_size(state: AgentState) -> int:
        context = ResponseGenerationContext.from_state(cast(RuntimeStateInput, state))
        return (
            len(context.user_input)
            + len(context.conversation_summary or "")
            + len(str(context.history))
            + len(str(context.knowledge_chunks))
            + len(str(context.user_memory or {}))
            + len(str(context.project_configuration or {}))
            + len(str(context.dialog_state or {}))
        )

    def _get_response_output_size(result: dict[str, object]) -> int:
        return len(str(result.get("response_text") or ""))

    async def response_generator_node(state: AgentState) -> dict[str, object]:
        return await log_node_execution(
            "response_generator",
            _response_generator_node_impl,
            state,
            get_input_size=_get_response_input_size,
            get_output_size=_get_response_output_size,
        )

    return response_generator_node
