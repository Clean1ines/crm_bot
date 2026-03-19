"""
Router node for LangGraph pipeline with model selection, rate limit handling,
and hybrid KB + reasoning synthesis.

This module selects the best available Groq model, builds a strict JSON prompt,
and routes the state into one of the supported decisions:
RESPOND_KB, RESPOND_TEMPLATE, LLM_GENERATE, CALL_TOOL, ESCALATE_TO_HUMAN.

The router is intentionally synthesis-first:
- KB results are treated as evidence, not raw copy-paste.
- Multi-question inputs are answered point-by-point.
- Low-confidence or sensitive requests still escalate.
"""

from __future__ import annotations

import asyncio
import json
import re
from textwrap import dedent
from typing import Any, Dict, List, Optional, Sequence, Tuple

from langchain_groq import ChatGroq
from pydantic import ValidationError

from src.agent.schemas import RouterOutput
from src.agent.state import AgentState
from src.core.config import settings
from src.core.logging import get_logger
from src.core.model_registry import ModelRegistry
from src.services.model_selector import ModelSelector
from src.services.rate_limit_tracker import RateLimitTracker

logger = get_logger(__name__)

# Global singletons for dependencies (lazy init)
_registry: Optional[ModelRegistry] = None
_tracker: Optional[RateLimitTracker] = None
_selector: Optional[ModelSelector] = None

# Central thresholds with safe fallbacks to configuration values.
DEFAULT_KB_THRESHOLD = float(
    getattr(settings, "ROUTER_KB_THRESHOLD", getattr(settings, "KB_THRESHOLD", 0.78))
)
DEFAULT_LLM_THRESHOLD = float(
    getattr(settings, "ROUTER_LLM_THRESHOLD", getattr(settings, "LLM_THRESHOLD", 0.70))
)
DEFAULT_ROUTER_TIMEOUT_SECONDS = float(
    getattr(settings, "ROUTER_TIMEOUT_SECONDS", 30.0)
)
DEFAULT_ROUTER_MAX_ATTEMPTS = int(
    getattr(settings, "ROUTER_MAX_ATTEMPTS", 3)
)
DEFAULT_KB_LIMIT = int(
    getattr(settings, "ROUTER_KB_LIMIT", 5)
)

SENSITIVE_KEYWORDS = (
    "refund",
    "chargeback",
    "возврат",
    "верните деньги",
    "деньги",
    "жалоб",
    "мошен",
    "обман",
    "угрож",
    "публичн",
    "удалить аккаунт",
    "отключить",
)

COMPLEXITY_KEYWORDS = (
    "интеграц",
    "подключ",
    "api",
    "postgres",
    "crm",
    "webhook",
    "n8n",
    "google sheets",
    "автоматизац",
    "oauth",
    "база данных",
    "бд",
    "сложн",
    "кастом",
)


def _get_registry() -> ModelRegistry:
    """
    Return the lazily initialized global ModelRegistry.

    Returns:
        ModelRegistry singleton.
    """
    global _registry
    if _registry is None:
        _registry = ModelRegistry()
    return _registry


def _get_tracker() -> RateLimitTracker:
    """
    Return the lazily initialized global RateLimitTracker.

    Returns:
        RateLimitTracker singleton.
    """
    global _tracker
    if _tracker is None:
        _tracker = RateLimitTracker()
    return _tracker


def _get_selector() -> ModelSelector:
    """
    Return the lazily initialized global ModelSelector.

    Returns:
        ModelSelector singleton.
    """
    global _selector
    if _selector is None:
        _selector = ModelSelector(_get_registry(), _get_tracker())
    return _selector


def _compact_whitespace(text: str) -> str:
    """
    Normalize whitespace so prompt contexts stay compact and cheap.

    Args:
        text: Arbitrary text.

    Returns:
        Text with consecutive whitespace collapsed into single spaces.
    """
    return re.sub(r"\s+", " ", text or "").strip()


def _truncate_text(text: str, max_length: int = 280) -> str:
    """
    Truncate text to a safe prompt size while keeping it readable.

    Args:
        text: Input text.
        max_length: Maximum allowed length.

    Returns:
        Truncated text with ellipsis if needed.
    """
    normalized = _compact_whitespace(text)
    if len(normalized) <= max_length:
        return normalized
    return normalized[: max_length - 1].rstrip() + "…"


def _safe_json_dumps(value: Any, *, indent: int = 2) -> str:
    """
    Serialize values to JSON safely for prompt/debug usage.

    Args:
        value: Any serializable value.
        indent: Indentation level.

    Returns:
        JSON string or a safe string fallback.
    """
    try:
        return json.dumps(value, ensure_ascii=False, indent=indent, default=str)
    except (TypeError, ValueError):
        return json.dumps(str(value), ensure_ascii=False, indent=indent)


def _extract_kb_text(item: Any) -> str:
    """
    Extract a human-readable knowledge snippet from KB result items.

    Supports multiple schemas:
    - {"answer": "..."}
    - {"content": "..."}
    - {"text": "..."}
    - raw strings

    Args:
        item: KB result item.

    Returns:
        Normalized text snippet or an empty string.
    """
    if isinstance(item, str):
        return _compact_whitespace(item)

    if isinstance(item, dict):
        for key in ("answer", "content", "text", "snippet", "reply"):
            value = item.get(key)
            if value:
                return _compact_whitespace(str(value))
    return ""


def _format_kb_results(
    kb_results: Sequence[Any],
    limit: int = DEFAULT_KB_LIMIT,
) -> Tuple[str, float, int]:
    """
    Format KB search results into a compact prompt-friendly evidence block.

    Args:
        kb_results: Sequence of KB results, usually dicts with score/content.
        limit: Maximum number of results to include.

    Returns:
        A tuple of:
        - compact textual evidence block
        - top score
        - number of included items
    """
    if not kb_results:
        return "[]", 0.0, 0

    lines: List[str] = []
    top_score = 0.0

    for index, item in enumerate(kb_results[:limit], start=1):
        score = 0.0
        text = ""
        question = ""
        method = ""

        if isinstance(item, dict):
            raw_score = item.get("score", 0.0)
            try:
                score = float(raw_score or 0.0)
            except (TypeError, ValueError):
                score = 0.0

            text = _extract_kb_text(item)
            question = _truncate_text(str(item.get("question", "")), 120)
            method = _compact_whitespace(str(item.get("method", "")))

        else:
            text = _extract_kb_text(item)

        top_score = max(top_score, score)

        parts: List[str] = [f"{index}. score={score:.3f}"]
        if question:
            parts.append(f"question={question}")
        if method:
            parts.append(f"method={method}")
        if text:
            parts.append(f"text={_truncate_text(text, 420)}")

        lines.append(" | ".join(parts))

    return "\n".join(lines), top_score, len(lines)


def _format_history(history: Sequence[Any], limit: int = 5) -> str:
    """
    Format recent message history into a compact prompt-friendly trace.

    Args:
        history: Sequence of history items (dicts or strings).
        limit: Maximum number of entries to include.

    Returns:
        Compact textual history representation.
    """
    if not history:
        return "[]"

    lines: List[str] = []
    for item in history[-limit:]:
        if isinstance(item, dict):
            role = _compact_whitespace(str(item.get("role", "message")))
            content = _truncate_text(str(item.get("content", "")), 220)
            if content:
                lines.append(f"- {role}: {content}")
        else:
            content = _truncate_text(str(item), 220)
            if content:
                lines.append(f"- {content}")

    return "\n".join(lines) if lines else "[]"


def _count_question_signals(text: str) -> int:
    """
    Estimate how many sub-questions are embedded in a user message.

    This is used for routing and model-selection heuristics only.

    Args:
        text: User message.

    Returns:
        Estimated number of question signals.
    """
    if not text:
        return 0

    lowered = text.lower()
    question_marks = text.count("?")
    interrogatives = len(
        re.findall(
            r"\b(что|как|сколько|почему|когда|где|зачем|какой|какая|какие|можно ли|есть ли)\b",
            lowered,
        )
    )

    # Blend punctuation and interrogative markers.
    return max(question_marks, interrogatives)


def _has_sensitive_or_urgent_intent(text: str) -> bool:
    """
    Detect sensitive or urgent intent that should bias toward a stronger model.

    Args:
        text: User message.

    Returns:
        True if the message contains sensitive or urgent intent.
    """
    lowered = (text or "").lower()
    return any(keyword in lowered for keyword in SENSITIVE_KEYWORDS)


def _has_complex_intent(text: str) -> bool:
    """
    Detect requests that typically benefit from a larger model.

    Args:
        text: User message.

    Returns:
        True if the message likely needs stronger reasoning.
    """
    lowered = (text or "").lower()
    return any(keyword in lowered for keyword in COMPLEXITY_KEYWORDS)


def _infer_routing_mode(
    kb_count: int,
    top_score: float,
    question_count: int,
    kb_threshold: float,
) -> str:
    """
    Infer a high-level routing mode for prompt steering and model selection.

    Args:
        kb_count: Number of KB results available.
        top_score: Best KB score.
        question_count: Estimated number of question signals.
        kb_threshold: Threshold for high-confidence KB usage.

    Returns:
        One of:
        - DIRECT_KB
        - HYBRID_SYNTHESIS
        - KB_AUGMENTED_LLM
        - LLM_ONLY
    """
    if kb_count <= 0:
        return "LLM_ONLY"

    if top_score >= kb_threshold and question_count <= 1:
        return "DIRECT_KB"

    if question_count >= 2 or kb_count >= 2:
        return "HYBRID_SYNTHESIS"

    return "KB_AUGMENTED_LLM"


def _build_router_prompt(
    *,
    user_input: str,
    client_profile: str,
    conversation_summary: str,
    recent_history: str,
    kb_context: str,
    kb_top_score: float,
    kb_count: int,
    question_count: int,
    routing_mode: str,
    kb_threshold: float,
    llm_threshold: float,
) -> str:
    """
    Build the router prompt used by the Groq model.

    The prompt is intentionally synthesis-first:
    - KB results are evidence, not raw copy-paste.
    - Multiple questions must be answered point-by-point.
    - Missing profile data should not block an answer unless required.

    Args:
        user_input: Current user message.
        client_profile: Serialized client profile.
        conversation_summary: Serialized conversation summary.
        recent_history: Serialized recent history.
        kb_context: Serialized KB evidence block.
        kb_top_score: Best KB score.
        kb_count: Number of KB results.
        question_count: Estimated number of question signals.
        routing_mode: Derived routing mode.
        kb_threshold: KB confidence threshold.
        llm_threshold: LLM confidence threshold.

    Returns:
        Fully rendered prompt string.
    """
    return dedent(
        f"""
        Ты — routing LLM и синтезатор ответа для клиентского бота MRAK-OS.

        Твоя задача:
        1) выбрать один из режимов: RESPOND_KB, RESPOND_TEMPLATE, LLM_GENERATE, CALL_TOOL, ESCALATE_TO_HUMAN;
        2) использовать KB как факты, а не как сырой копипаст;
        3) если в сообщении несколько вопросов — ответить на каждый по пунктам;
        4) если KB покрывает только часть запроса — ответить на то, что известно, и кратко обозначить неизвестное;
        5) не блокировать ответ только потому, что client_profile пустой;
        6) эскалировать только когда это действительно нужно.

        Текущий режим маршрутизации: {routing_mode}
        Количество вопросительных сигналов: {question_count}

        Входные данные:
        - user_input: {user_input}
        - client_profile: {client_profile}
        - conversation_summary: {conversation_summary}
        - recent_history: {recent_history}
        - kb_context:
        {kb_context}
        - kb_top_score: {kb_top_score:.3f}
        - kb_count: {kb_count}
        - kb_threshold: {kb_threshold:.3f}
        - llm_threshold: {llm_threshold:.3f}

        Правила:
        1) Если запрос злой, содержит жалобу, возврат денег, chargeback, публичный негатив, угрозу или явный запрос человека — ESCALATE_TO_HUMAN.
        2) Если ответ можно уверенно собрать из KB, выбери RESPOND_KB и синтезируй связный ответ своими словами.
        3) Если есть несколько релевантных KB-фрагментов или несколько вопросов — ответь по пунктам и не потеряй ни один вопрос.
        4) RESPOND_TEMPLATE используй только для действительно шаблонных сценариев.
        5) LLM_GENERATE используй, когда KB не покрывает вопрос полностью или нужна дополнительная логика.
        6) Если client_profile отсутствует, не делай из этого блокер; запроси данные только если без них нельзя продолжить.
        7) Не копируй KB дословно, если можешь ответить лучше, короче и понятнее.
        8) Ответ пиши по-русски, вежливо и по делу, без лишней воды.

        Формат ответа (только JSON):
        {{
          "decision": "RESPOND_KB | RESPOND_TEMPLATE | LLM_GENERATE | CALL_TOOL | ESCALATE_TO_HUMAN",
          "response": "string",
          "tool": "string|null",
          "tool_args": {{}},
          "requires_human": true|false,
          "confidence": 0.0
        }}

        Примеры:

        Input: "Сколько стоит доставка? И какие сроки?"
        kb_context:
        1. score=0.920 | answer: Доставка стоит 300 рублей.
        2. score=0.840 | answer: Обычно доставка занимает 1-3 рабочих дня.
        → Output: {{"decision":"RESPOND_KB","response":"Доставка стоит 300 рублей. Обычно доставка занимает 1-3 рабочих дня.","tool":null,"tool_args":{{}},"requires_human":false,"confidence":0.92}}

        Input: "Хочу подключить нашу Postgres базу и OAuth"
        → Output: {{"decision":"ESCALATE_TO_HUMAN","response":"Это уже настройка интеграции. Я передал запрос менеджеру.","tool":"ticket.create","tool_args":{{"priority":"high"}},"requires_human":true,"confidence":0.95}}

        Возвращай ТОЛЬКО JSON, без пояснений.
        """
    ).strip()


def _clean_response_content(content: str) -> str:
    """
    Clean model response from markdown code fences or wrapper text.

    Args:
        content: Raw model output.

    Returns:
        Clean JSON string candidate.
    """
    cleaned = (content or "").strip()

    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", cleaned, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        cleaned = fenced.group(1).strip()
    else:
        object_match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if object_match:
            cleaned = object_match.group(0).strip()

    return cleaned


def _validate_router_output(data: Dict[str, Any]) -> RouterOutput:
    """
    Validate parsed router JSON with the project's RouterOutput schema.

    Args:
        data: Parsed JSON dictionary.

    Returns:
        Validated RouterOutput object.
    """
    if hasattr(RouterOutput, "model_validate"):
        return RouterOutput.model_validate(data)  # type: ignore[attr-defined]
    return RouterOutput.parse_obj(data)  # type: ignore[attr-defined]


def _parse_router_output(content: str) -> RouterOutput:
    """
    Parse and validate router output from the model.

    Args:
        content: Raw model text output.

    Returns:
        Validated RouterOutput object.

    Raises:
        JSONDecodeError: If the content is not valid JSON.
        ValidationError: If the JSON does not match RouterOutput schema.
    """
    cleaned = _clean_response_content(content)
    data = json.loads(cleaned)
    return _validate_router_output(data)


def _build_fallback_response_from_kb(
    *,
    kb_results: Sequence[Any],
    user_input: str,
) -> str:
    """
    Build a deterministic fallback answer from KB evidence.

    Used only when the model output cannot be parsed or the generation fails.

    Args:
        kb_results: KB evidence.
        user_input: Original user message.

    Returns:
        Human-readable fallback answer.
    """
    items: List[str] = []

    for item in kb_results[:3]:
        text = _extract_kb_text(item)
        if text:
            items.append(f"- {_truncate_text(text, 320)}")

    if not items:
        return (
            "Сейчас я не смог сформировать корректный ответ. "
            "Я передал запрос менеджеру."
        )

    intro = "Нашёл релевантные сведения:\n"
    outro = (
        "\n\nЕсли хочешь, я могу уточнить вопрос и сузить ответ под твой кейс."
    )

    # If the user asked multiple questions, keep the fallback point-by-point.
    if _count_question_signals(user_input) >= 2:
        intro = "Нашёл несколько релевантных фрагментов и собрал краткий ответ:\n"

    return intro + "\n".join(items) + outro


def _extract_model_id(candidate: Any) -> str:
    """
    Extract a model identifier from a registry item.

    Args:
        candidate: Registry entry returned by ModelRegistry.

    Returns:
        Model ID string.
    """
    if isinstance(candidate, dict):
        return str(
            candidate.get("id")
            or candidate.get("model")
            or candidate.get("name")
            or ""
        )
    return str(candidate or "")


def _build_llm_client(model_id: str, override_llm: Optional[ChatGroq] = None) -> ChatGroq:
    """
    Build a ChatGroq client for the selected model.

    Args:
        model_id: Groq model identifier.
        override_llm: Optional injected LLM instance.

    Returns:
        ChatGroq instance.
    """
    if override_llm is not None:
        return override_llm

    return ChatGroq(
        model=model_id,
        temperature=0.0,
        api_key=settings.GROQ_API_KEY,
    )


def create_router_node(
    llm: Optional[ChatGroq] = None,
    registry: Optional[ModelRegistry] = None,
    tracker: Optional[RateLimitTracker] = None,
    selector: Optional[ModelSelector] = None,
):
    """
    Factory function that creates a router node with model selection and rate limit handling.

    The node now behaves as a hybrid KB + reasoning router:
    - the prompt encourages synthesis across multiple KB snippets;
    - KB hits are not treated as raw copy-paste answers;
    - multi-question requests are answered point-by-point;
    - routing decisions remain JSON-only and schema-validated.

    Args:
        llm: Optional ChatGroq instance (kept for compatibility and tests).
        registry: Optional ModelRegistry instance. If None, a global singleton is used.
        tracker: Optional RateLimitTracker instance. If None, a global singleton is used.
        selector: Optional ModelSelector instance. If None, a selector is created from registry/tracker.

    Returns:
        An async function that takes an AgentState dict and returns a dict
        with the router's decision and related fields.
    """
    reg = registry if registry is not None else _get_registry()
    trk = tracker if tracker is not None else _get_tracker()
    sel = selector if selector is not None else ModelSelector(reg, trk)

    async def router_node(state: AgentState) -> Dict[str, Any]:
        """
        Analyze the current state and decide the next action with a Groq model.

        This node:
        - prepares compact KB and history context;
        - selects the best model based on complexity and rate limits;
        - retries with alternative models on 429;
        - validates strict JSON output;
        - falls back to deterministic KB synthesis if the model output is invalid.

        Args:
            state: Current agent state.

        Returns:
            Dictionary with normalized router output fields.
        """
        user_input = (state.get("user_input") or "").strip()
        project_id = state.get("project_id")
        thread_id = state.get("thread_id")
        conversation_summary = _truncate_text(
            str(state.get("conversation_summary") or "Нет краткого содержания."),
            600,
        )
        client_profile = state.get("client_profile")
        history = state.get("history") or []
        raw_kb_results = state.get("knowledge_chunks") or state.get("kb_results") or []

        if not user_input:
            logger.warning(
                "router_node called with empty user_input",
                project_id=project_id,
                thread_id=thread_id,
            )
            return {
                "decision": "ESCALATE_TO_HUMAN",
                "requires_human": True,
                "response_text": "Не удалось обработать запрос (пустой ввод). Передано менеджеру.",
                "confidence": 0.0,
                "tool_name": None,
                "tool_args": {},
            }

        kb_context, top_score, kb_count = _format_kb_results(raw_kb_results)
        question_count = _count_question_signals(user_input)
        routing_mode = _infer_routing_mode(
            kb_count=kb_count,
            top_score=top_score,
            question_count=question_count,
            kb_threshold=DEFAULT_KB_THRESHOLD,
        )

        complex_needed = (
            routing_mode in {"HYBRID_SYNTHESIS", "KB_AUGMENTED_LLM", "LLM_ONLY"}
            or len(user_input) > 120
            or _has_complex_intent(user_input)
            or _has_sensitive_or_urgent_intent(user_input)
        )

        model_id = await sel.get_best_model(complex_needed=complex_needed)
        logger.info(
            "Selected model for router",
            model=model_id,
            complex_needed=complex_needed,
            routing_mode=routing_mode,
            project_id=project_id,
            thread_id=thread_id,
            kb_count=kb_count,
            top_score=round(top_score, 3),
        )

        prompt = _build_router_prompt(
            user_input=user_input,
            client_profile=_safe_json_dumps(client_profile if client_profile is not None else None),
            conversation_summary=conversation_summary,
            recent_history=_format_history(history, limit=5),
            kb_context=kb_context,
            kb_top_score=top_score,
            kb_count=kb_count,
            question_count=question_count,
            routing_mode=routing_mode,
            kb_threshold=DEFAULT_KB_THRESHOLD,
            llm_threshold=DEFAULT_LLM_THRESHOLD,
        )

        logger.debug(
            "Router context prepared",
            project_id=project_id,
            thread_id=thread_id,
            user_input_preview=_truncate_text(user_input, 120),
            kb_count=kb_count,
            question_count=question_count,
            routing_mode=routing_mode,
        )

        if llm is not None:
            logger.debug(
                "Using injected LLM instance for router first attempt",
                project_id=project_id,
                thread_id=thread_id,
            )

        current_llm = _build_llm_client(model_id, override_llm=llm)
        used_models = {model_id}
        response = None
        last_error: Optional[Exception] = None

        for attempt in range(DEFAULT_ROUTER_MAX_ATTEMPTS):
            try:
                logger.debug(
                    "Calling router LLM",
                    attempt=attempt + 1,
                    model=model_id,
                    project_id=project_id,
                    thread_id=thread_id,
                )
                response = await asyncio.wait_for(
                    current_llm.ainvoke(prompt),
                    timeout=DEFAULT_ROUTER_TIMEOUT_SECONDS,
                )
                last_error = None
                break
            except asyncio.TimeoutError as exc:
                last_error = exc
                logger.warning(
                    "Router LLM timed out",
                    attempt=attempt + 1,
                    model=model_id,
                    timeout_seconds=DEFAULT_ROUTER_TIMEOUT_SECONDS,
                    project_id=project_id,
                    thread_id=thread_id,
                )
            except Exception as exc:
                last_error = exc
                error_message = str(exc).lower()

                if "429" in error_message or "rate limit" in error_message:
                    logger.warning(
                        "Router model hit rate limit",
                        attempt=attempt + 1,
                        model=model_id,
                        project_id=project_id,
                        thread_id=thread_id,
                    )

                    if attempt < DEFAULT_ROUTER_MAX_ATTEMPTS - 1:
                        candidate_models = reg.get_models_sorted_by_priority(complex_needed)
                        switched = False

                        for candidate in candidate_models:
                            candidate_model_id = _extract_model_id(candidate)
                            if candidate_model_id and candidate_model_id not in used_models:
                                model_id = candidate_model_id
                                used_models.add(candidate_model_id)
                                current_llm = _build_llm_client(model_id)
                                switched = True
                                logger.info(
                                    "Switching to alternative router model",
                                    model=model_id,
                                    attempt=attempt + 1,
                                    project_id=project_id,
                                    thread_id=thread_id,
                                )
                                break

                        if not switched:
                            fallback_model = str(
                                getattr(settings, "DEFAULT_MODEL", model_id)
                            )
                            if fallback_model not in used_models:
                                model_id = fallback_model
                                used_models.add(fallback_model)
                                current_llm = _build_llm_client(model_id)
                                logger.warning(
                                    "Falling back to default router model",
                                    model=model_id,
                                    project_id=project_id,
                                    thread_id=thread_id,
                                )
                            else:
                                logger.warning(
                                    "No unused alternative model found for router retry",
                                    project_id=project_id,
                                    thread_id=thread_id,
                                )
                        continue

                    logger.error(
                        "All router attempts were rate-limited",
                        project_id=project_id,
                        thread_id=thread_id,
                    )
                    break

                logger.exception(
                    "Router LLM call failed",
                    model=model_id,
                    project_id=project_id,
                    thread_id=thread_id,
                )
                raise

        if response is None:
            fallback_text = _build_fallback_response_from_kb(
                kb_results=raw_kb_results,
                user_input=user_input,
            )
            if raw_kb_results:
                logger.warning(
                    "Router fell back to deterministic KB synthesis",
                    project_id=project_id,
                    thread_id=thread_id,
                    kb_count=kb_count,
                )
                return {
                    "decision": "RESPOND_KB",
                    "response_text": fallback_text,
                    "tool_name": None,
                    "tool_args": {},
                    "requires_human": False,
                    "confidence": max(0.55, min(0.85, top_score or 0.55)),
                }

            logger.error(
                "Router could not obtain an LLM response and has no KB fallback",
                project_id=project_id,
                thread_id=thread_id,
                last_error=str(last_error) if last_error else None,
            )
            return {
                "decision": "ESCALATE_TO_HUMAN",
                "requires_human": True,
                "response_text": "Произошла техническая ошибка при обработке запроса. Передано менеджеру.",
                "confidence": 0.0,
                "tool_name": None,
                "tool_args": {},
            }

        raw_content = getattr(response, "content", "") or ""
        try:
            router_output = _parse_router_output(raw_content)
            logger.debug(
                "Router output validated",
                decision=router_output.decision,
                project_id=project_id,
                thread_id=thread_id,
            )
        except (json.JSONDecodeError, ValidationError) as exc:
            logger.error(
                "Failed to parse or validate router output",
                error=str(exc),
                raw_preview=_truncate_text(raw_content, 500),
                project_id=project_id,
                thread_id=thread_id,
            )

            fallback_text = _build_fallback_response_from_kb(
                kb_results=raw_kb_results,
                user_input=user_input,
            )

            if raw_kb_results:
                return {
                    "decision": "RESPOND_KB",
                    "response_text": fallback_text,
                    "tool_name": None,
                    "tool_args": {},
                    "requires_human": False,
                    "confidence": max(0.5, min(0.8, top_score or 0.5)),
                }

            return {
                "decision": "ESCALATE_TO_HUMAN",
                "requires_human": True,
                "response_text": "Произошла ошибка при обработке запроса. Передано менеджеру.",
                "confidence": 0.0,
                "tool_name": None,
                "tool_args": {},
            }

        decision = getattr(router_output, "decision", None) or "LLM_GENERATE"
        response_text = (getattr(router_output, "response", "") or "").strip()
        tool_name = getattr(router_output, "tool", None)
        tool_args = getattr(router_output, "tool_args", None) or {}
        requires_human = bool(
            getattr(router_output, "requires_human", False)
            or decision == "ESCALATE_TO_HUMAN"
        )
        confidence = float(getattr(router_output, "confidence", 0.0) or 0.0)

        # Normalization rules keep the router resilient and preserve a helpful response.
        if decision == "CALL_TOOL" and not tool_name:
            logger.warning(
                "Router requested CALL_TOOL without tool name; escalating",
                project_id=project_id,
                thread_id=thread_id,
            )
            return {
                "decision": "ESCALATE_TO_HUMAN",
                "requires_human": True,
                "response_text": "Запрос требует дополнительной обработки. Я передал его менеджеру.",
                "confidence": max(confidence, 0.5),
                "tool_name": None,
                "tool_args": {},
            }

        if not response_text and raw_kb_results:
            response_text = _build_fallback_response_from_kb(
                kb_results=raw_kb_results,
                user_input=user_input,
            )

        if not response_text and decision != "ESCALATE_TO_HUMAN":
            response_text = (
                "Сейчас не удалось сформировать точный ответ. "
                "Если хочешь, я передам вопрос менеджеру."
            )

        if decision == "ESCALATE_TO_HUMAN" and not response_text:
            response_text = "Я передал запрос менеджеру."

        result = {
            "decision": decision,
            "response_text": response_text,
            "tool_name": tool_name,
            "tool_args": tool_args,
            "requires_human": requires_human,
            "confidence": confidence,
        }

        logger.info(
            "Router decision finalized",
            decision=result["decision"],
            confidence=result["confidence"],
            requires_human=result["requires_human"],
            model_used=model_id,
            project_id=project_id,
            thread_id=thread_id,
            kb_count=kb_count,
            top_score=round(top_score, 3),
            routing_mode=routing_mode,
        )
        return result

    return router_node
