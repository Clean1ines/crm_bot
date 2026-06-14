"""
Response generator node for the LangGraph pipeline.

Uses the configured LLM to craft the final answer from decision, history,
knowledge, memory, and project runtime configuration.
"""

from collections.abc import Mapping
from typing import Protocol, cast

from src.agent.router.prompt_builder import build_response_prompt
from src.agent.state import AgentState
from src.domain.runtime.language_policy import (
    detect_language_hint,
    normalize_project_language,
)
from src.domain.runtime.project_runtime_profile import ProjectRuntimeProfile
from src.domain.runtime.response_generation import (
    ResponseGenerationContext,
    ResponseGenerationResult,
)
from src.domain.runtime.state_contracts import RuntimeHistoryMessage, RuntimeStateInput
from src.infrastructure.config.settings import settings
from src.infrastructure.logging.logger import get_logger, log_node_execution

logger = get_logger(__name__)

TECHNICAL_FAILURE_FIRST_TEXT = (
    "Не получилось сгенерировать ответ из-за технической ошибки. "
    "Можете повторить запрос, а если вопрос срочный — я передам диалог менеджеру."
)

TECHNICAL_FAILURE_REPEAT_TEXT = (
    "Похоже, техническая ошибка повторилась. Я уже передал технический инцидент "
    "владельцу проекта. Можете позвать менеджера, чтобы не ждать восстановления ассистента."
)

LANGUAGE_MISMATCH_FALLBACK_RU = (
    "Хочу ответить на вашем языке корректно. "
    "Уточните, пожалуйста, вопрос ещё раз, и я помогу."
)
LANGUAGE_MISMATCH_FALLBACK_EN = (
    "I want to respond correctly in your language. "
    "Please rephrase your question, and I will help."
)
LANGUAGE_MISMATCH_FALLBACK_DE = (
    "Ich möchte korrekt in Ihrer Sprache antworten. "
    "Bitte formulieren Sie Ihre Frage noch einmal, dann helfe ich Ihnen."
)
LANGUAGE_MISMATCH_FALLBACK_ES = (
    "Quiero responder correctamente en su idioma. "
    "Por favor, reformule su pregunta y le ayudaré."
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


class ChatGroqClientFactory(Protocol):
    def __call__(self, *, api_key: str) -> ChatGroqClient: ...


# Test hook and lazy runtime cache.
# Keep this symbol module-level so existing tests can patch
# src.agent.nodes.response_generator.ChatGroq without importing langchain_groq
# at import time.
ChatGroq: ChatGroqFactory | None = None


def _primary_groq_api_key() -> str:
    value = str(settings.GROQ_API_KEY).strip()
    if not value:
        raise RuntimeError("GROQ_API_KEY is not configured")
    return value


async def _ainvoke_chat_once(
    *,
    make_client: ChatGroqClientFactory,
    messages: list[tuple[str, str]],
) -> ChatMessageResponse:
    client = make_client(api_key=_primary_groq_api_key())
    return await client.ainvoke(messages)


def _chat_groq_class() -> ChatGroqFactory:
    if ChatGroq is not None:
        return ChatGroq

    from langchain_groq import ChatGroq as ImportedChatGroq

    return cast(ChatGroqFactory, ImportedChatGroq)


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


def _project_target_language(state: AgentState) -> str:
    configuration = state.get("project_configuration")
    settings_block: Mapping[str, object] = {}
    if isinstance(configuration, Mapping):
        raw_settings = configuration.get("settings")
        if isinstance(raw_settings, Mapping):
            settings_block = raw_settings

    target = normalize_project_language(
        str(settings_block.get("target_language") or "")
    )

    profile = ProjectRuntimeProfile.from_configuration(configuration)
    if target == "unknown":
        target = normalize_project_language(profile.target_language)
    if target == "unknown":
        target = normalize_project_language(profile.default_language)
    return target


def _language_mismatch_fallback(target_language: str) -> str:
    if target_language == "en":
        return LANGUAGE_MISMATCH_FALLBACK_EN
    if target_language == "de":
        return LANGUAGE_MISMATCH_FALLBACK_DE
    if target_language == "es":
        return LANGUAGE_MISMATCH_FALLBACK_ES
    return LANGUAGE_MISMATCH_FALLBACK_RU


def _technical_failure_patch(state: AgentState, exc: Exception) -> dict[str, object]:
    previous_count = _coerce_int(state.get("technical_failure_count"), 0)
    next_count = previous_count + 1

    response_text = (
        TECHNICAL_FAILURE_REPEAT_TEXT
        if next_count >= 2
        else TECHNICAL_FAILURE_FIRST_TEXT
    )

    patch = dict(
        ResponseGenerationResult(
            response_text=response_text,
        ).to_state_patch()
    )
    patch.update(
        {
            "technical_failure_count": next_count,
            "technical_failure_stage": "response_generator",
            "technical_failure_error": type(exc).__name__,
            "requires_human": False,
        }
    )

    patch["technical_incident_created"] = bool(
        state.get("technical_incident_created") or False
    )

    return patch


def create_response_generator_node(
    llm: ChatGroqClient | None = None,
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
                "commercial_context_status": context.commercial_context_status,
                "has_dialog_state": bool(context.dialog_state),
            },
        )

        prompt = build_response_prompt(
            decision=context.decision,
            user_input=context.user_input,
            conversation_summary=context.conversation_summary,
            history=_prompt_history(context.history),
            knowledge_chunks=context.knowledge_chunks,
            commercial_context=context.commercial_context,
            user_memory=merged_memory,
            features=_prompt_features(context.features),
            project_configuration=context.project_configuration,
            target_language=_project_target_language(state),
        )

        try:
            selected_model = _resolve_response_model_name(state, base_model)
            messages = [("human", prompt)]

            if llm is not None and selected_model == base_model:
                response = await llm.ainvoke(messages)
            else:

                def _make_client(*, api_key: str) -> ChatGroqClient:
                    return _chat_groq_class()(
                        model=selected_model,
                        temperature=0.3,
                        max_tokens=500,
                        api_key=api_key,
                    )

                response = await _ainvoke_chat_once(
                    make_client=_make_client,
                    messages=messages,
                )
            response_text = (response.content or "").strip()
            input_lang = detect_language_hint(context.user_input)
            target_lang = _project_target_language(state)
            if target_lang == "unknown":
                target_lang = input_lang
            output_lang = detect_language_hint(response_text)
            if (
                response_text
                and target_lang != "unknown"
                and output_lang != "unknown"
                and target_lang != output_lang
            ):
                logger.warning(
                    "Response language mismatch detected; using safe fallback",
                    extra={
                        "input_lang": input_lang,
                        "target_lang": target_lang,
                        "output_lang": output_lang,
                        "decision": context.decision,
                    },
                )
                response_text = _language_mismatch_fallback(target_lang)

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
                    "policy": "technical_failure_user_choice",
                },
            )
            return _technical_failure_patch(state, exc)

    def _get_response_input_size(state: AgentState) -> int:
        context = ResponseGenerationContext.from_state(cast(RuntimeStateInput, state))
        return (
            len(context.user_input)
            + len(context.conversation_summary or "")
            + len(str(context.history))
            + len(str(context.knowledge_chunks))
            + len(str(context.commercial_context or {}))
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
