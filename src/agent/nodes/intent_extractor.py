"""
Intent extraction node for LangGraph pipeline.

Uses a lightweight LLM to extract domain, intent, CTA, topic, emotion, and feature hints.
"""

from dataclasses import replace
import json
import os
import re
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

_HANDOFF_INFORMATION_TERMS = (
    "менеджер",
    "оператор",
    "handoff",
    "manager",
    "operator",
)
_HANDOFF_INFORMATION_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bчто\s+такое\b",
        r"\bкак\s+(?:работает|устроен|происходит|подключается|подключить|настроить)\b",
        r"\bкогда\s+(?:подключается|вызывается|нужен|нужна|нужно)\b",
        r"\b(?:зачем|для\s+чего)\s+(?:нужен|нужна|нужно|используется)\b",
        r"\bможно\s+ли\s+(?:настроить|подключить|добавить)\b",
        r"\bчем\s+отличается\b",
        r"\bв\s+каких\s+случаях\b",
    )
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
        reasoning_effort: str,
        api_key: object,
        model_kwargs: dict[str, object],
    ) -> ChatGroqClient: ...


class ChatGroqClientFactory(Protocol):
    def __call__(self, *, api_key: str) -> ChatGroqClient: ...


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


def _rag_debug_enabled() -> bool:
    return os.getenv("RAG_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}


def _preview_text(value: object, limit: int = 160) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    if not text:
        return None
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


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


def _conversation_context_subject(value: object) -> object:
    if not isinstance(value, dict):
        return None
    return value.get("current_subject")


def _looks_like_handoff_information_question(text: str) -> bool:
    normalized = " ".join(str(text).strip().casefold().split())
    if not normalized:
        return False
    if not any(term in normalized for term in _HANDOFF_INFORMATION_TERMS):
        return False
    return any(pattern.search(normalized) for pattern in _HANDOFF_INFORMATION_PATTERNS)


def _restore_semantic_handoff(
    result: IntentExtractionResult,
    *,
    payload: object,
    user_input: str,
) -> IntentExtractionResult:
    """Trust an explicit LLM handoff intent when deterministic rules missed wording.

    Regex rules are a fast path, not an authorization gate. The existing domain
    normalization intentionally downgrades possible false-positive manager mentions;
    this adapter restores a genuine semantic handoff unless the utterance is clearly
    an informational question about the manager/handoff mechanism itself.
    """
    if not isinstance(payload, dict):
        return result
    raw_intent = str(payload.get("intent") or "").strip().lower()
    if raw_intent != "handoff_request":
        return result
    if not result.normalization_flags.get("handoff_intent_downgraded"):
        return result
    if _looks_like_handoff_information_question(user_input):
        return result

    flags = dict(result.normalization_flags)
    flags.pop("handoff_intent_downgraded", None)
    flags.pop("handoff_intent_downgrade_reason", None)
    flags["semantic_handoff_restored"] = True

    return replace(
        result,
        domain="business",
        intent="handoff_request",
        topic="handoff",
        cta="call_manager",
        resolved_cta="call_manager",
        resolved_cta_reply="affirmative",
        should_search_kb=False,
        should_generate_answer=False,
        should_offer_manager=False,
        knowledge_query=None,
        normalization_flags=flags,
    )


def create_intent_extractor_node(
    llm: ChatGroqClient | None = None,
    model_name: str = "openai/gpt-oss-120b",
):
    """
    Create the intent-extractor node with an optional lightweight LLM client.
    """

    base_model = model_name

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
            conversation_context=state.get("conversation_context"),
            recent_ticket_resolutions=state.get("recent_ticket_resolutions"),
        )

        try:
            messages = [("human", prompt)]
            if llm is not None:
                response = await llm.ainvoke(messages)
            else:

                def _make_client(*, api_key: str) -> ChatGroqClient:
                    return _chat_groq_class()(
                        model=base_model,
                        temperature=0.0,
                        max_tokens=1024,
                        reasoning_effort="low",
                        api_key=api_key,
                        model_kwargs={"response_format": {"type": "json_object"}},
                    )

                response = await _ainvoke_chat_once(
                    make_client=_make_client,
                    messages=messages,
                )
            payload = json.loads(_unwrap_json_block(str(response.content or "")))
            result = IntentExtractionResult.from_llm_payload(
                payload,
                user_input=context.user_input,
            ).normalized_for_context(context)
            result = _restore_semantic_handoff(
                result,
                payload=payload,
                user_input=context.user_input,
            )
            persisted_current_subject = _conversation_context_subject(
                state.get("conversation_context")
            )
            trace_extra: dict[str, object] = {
                "thread_id": state.get("thread_id"),
                "project_id": state.get("project_id"),
                "domain": result.domain,
                "turn_relation": result.turn_relation,
                "intent": result.intent,
                "cta": result.cta,
                "topic": result.topic,
                "emotion": result.emotion,
                "is_repeat_like": result.is_repeat_like,
                "should_search_kb": result.should_search_kb,
                "should_generate_answer": result.should_generate_answer,
                "should_offer_manager": result.should_offer_manager,
                "resolved_cta": result.resolved_cta,
                "resolved_cta_reply": result.resolved_cta_reply,
                "repeat_relation": result.repeat_relation,
                "persisted_current_subject": persisted_current_subject,
                "model_proposed_subject": payload.get("current_subject"),
                "current_subject": result.current_subject,
                "dissatisfaction": result.dissatisfaction,
                "model_contextual_query_present": bool(payload.get("knowledge_query")),
                "final_knowledge_query_present": bool(result.knowledge_query),
                "knowledge_query_source": result.knowledge_query_source.value,
                "action_cta_downgraded": bool(
                    result.normalization_flags.get("action_cta_downgraded")
                ),
                "memory_candidate_count": len(result.memory_candidates),
                "accepted_memory_candidate_keys": [
                    str(candidate.get("key")) for candidate in result.memory_candidates
                ],
                "handoff_intent_downgraded": bool(
                    result.normalization_flags.get("handoff_intent_downgraded")
                ),
            }
            if _rag_debug_enabled():
                raw_unrecognized_feature_keys = result.normalization_flags.get(
                    "unrecognized_feature_keys", []
                )
                unrecognized_feature_keys = (
                    raw_unrecognized_feature_keys
                    if isinstance(raw_unrecognized_feature_keys, list)
                    else []
                )
                trace_extra.update(
                    {
                        "user_input_preview": _preview_text(context.user_input),
                        "model_contextual_query_preview": _preview_text(
                            payload.get("knowledge_query")
                        ),
                        "knowledge_query_preview": _preview_text(
                            result.knowledge_query
                        ),
                        "knowledge_query_rejected_reason": (
                            result.normalization_flags.get(
                                "knowledge_query_rejected_reason"
                            )
                        ),
                        "features": dict(result.features),
                        "unrecognized_feature_keys": list(unrecognized_feature_keys),
                        "normalization_flags": dict(result.normalization_flags),
                        "handoff_intent_downgrade_reason": (
                            result.normalization_flags.get(
                                "handoff_intent_downgrade_reason"
                            )
                        ),
                    }
                )
            logger.info("Intent extraction trace", extra=trace_extra)
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
                    "repeat_relation": result.repeat_relation,
                    "current_subject": result.current_subject,
                    "memory_candidate_count": len(result.memory_candidates),
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
