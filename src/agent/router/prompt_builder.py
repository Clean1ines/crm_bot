"""
Functions for building the router prompt from agent state and KB results.
"""

import json
from textwrap import dedent
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.core.config import settings
from src.core.logging import get_logger
from src.agent.router.utils import (
    truncate_text,
    extract_kb_text,
    compact_whitespace,
    count_question_signals,
)

logger = get_logger(__name__)

# Default values from settings (with fallback)
DEFAULT_KB_THRESHOLD = float(getattr(settings, "ROUTER_KB_THRESHOLD", getattr(settings, "KB_THRESHOLD", 0.78)))
DEFAULT_LLM_THRESHOLD = float(getattr(settings, "ROUTER_LLM_THRESHOLD", getattr(settings, "LLM_THRESHOLD", 0.70)))
DEFAULT_KB_LIMIT = int(getattr(settings, "ROUTER_KB_LIMIT", 5))


def format_kb_results(
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

            text = extract_kb_text(item)
            question = truncate_text(str(item.get("question", "")), 120)
            method = compact_whitespace(str(item.get("method", "")))
        else:
            # Non-dict item (shouldn't happen, but handle gracefully)
            text = extract_kb_text(item)

        top_score = max(top_score, score)

        parts: List[str] = [f"{index}. score={score:.3f}"]
        if question:
            parts.append(f"question={question}")
        if method:
            parts.append(f"method={method}")
        if text:
            parts.append(f"text={truncate_text(text, 420)}")

        lines.append(" | ".join(parts))

    return "\n".join(lines), top_score, len(lines)


def format_history(history: Sequence[Any], limit: int = 5) -> str:
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
            role = compact_whitespace(str(item.get("role", "message")))
            content = truncate_text(str(item.get("content", "")), 220)
            if content:
                lines.append(f"- {role}: {content}")
        else:
            content = truncate_text(str(item), 220)
            if content:
                lines.append(f"- {content}")

    return "\n".join(lines) if lines else "[]"


def infer_routing_mode(
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


def build_router_prompt(
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
