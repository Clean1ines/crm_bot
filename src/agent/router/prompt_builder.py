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


def _format_memory(memory_by_type: Dict[str, List[Dict]]) -> str:
    """
    Format long-term user memory into a readable prompt block.

    Args:
        memory_by_type: Dictionary mapping type to list of {key, value}.

    Returns:
        String representation, or empty string if no memory.
    """
    if not memory_by_type:
        return ""

    lines = []
    for typ, items in memory_by_type.items():
        lines.append(f"--- {typ.upper()} ---")
        for item in items:
            key = item.get("key", "?")
            val = item.get("value")
            if isinstance(val, dict):
                val_str = json.dumps(val, ensure_ascii=False)
            else:
                val_str = str(val)
            lines.append(f"  {key}: {truncate_text(val_str, 200)}")
    return "\n".join(lines)


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
    user_memory: Optional[Dict[str, List[Dict]]] = None,
) -> str:
    """
    Build the router prompt used by the Groq model.

    The prompt is intentionally synthesis-first:
    - KB results are evidence, not raw copy-paste.
    - Multiple questions must be answered point-by-point.
    - Missing profile data should not block an answer unless required.
    - Long-term user memory is included if available.

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
        user_memory: Optional dictionary of user memory by type.

    Returns:
        Fully rendered prompt string.
    """
    memory_block = ""
    if user_memory:
        mem_str = _format_memory(user_memory)
        if mem_str:
            memory_block = f"Память о пользователе:\n{mem_str}\n"

    return dedent(
        f"""
    Ты — AI-менеджер по продажам, который общается с клиентом в Telegram.

    Твоя задача:
    1) выбрать действие:
    RESPOND_KB | RESPOND_TEMPLATE | LLM_GENERATE | CALL_TOOL | ESCALATE_TO_HUMAN
    2) дать ответ клиенту
    3) довести его до следующего шага:
    - заявка
    - демо
    - подключение
    - передача менеджеру

    ---

    ТЫ НЕ ТЕХНИЧЕСКИЙ БОТ:

    - не используешь слова: API, webhook, RAG, LLM, routing и т.д.
    - не объясняешь систему
    - не звучишь как инженер
    - не пишешь длинно
    - не копируешь KB дословно

    Ты продаёшь результат.

    ---

    КАК ТЫ ОТВЕЧАЕШЬ:

    - коротко
    - по делу
    - по-человечески
    - 1 мысль = 1–3 предложения

    ---

    КАК ТЫ ИСПОЛЬЗУЕШЬ KB:

    - KB = источник фактов (цены, условия, правила)
    - НЕ игнорируй KB, если там есть ответ
    - НЕ придумывай, если KB уже содержит информацию
    - если KB покрывает вопрос → RESPOND_KB
    - если частично → дополни и объясни просто
    - если KB нет → LLM_GENERATE

    ---

    ЛОГИКА ПРОДАЖ:

    1) понять бизнес
    2) понять есть ли заявки
    3) показать выгоду (не терять клиентов, экономия времени)
    4) дать цену (если спрашивают)
    5) снять сомнение
    6) предложить следующий шаг

    ---

    ПРАВИЛА:

    - если вопрос про цену → отвечай сразу
    - если несколько вопросов → ответь по пунктам
    - если клиент сомневается → упростить
    - если клиент готов → веди к действию
    - если злится / требует человека → ESCALATE_TO_HUMAN

    ---

    СТРУКТУРА ОТВЕТА:

    ВСЕГДА:
    - короткий ответ
    - 1 фраза пользы
    - 1 следующий шаг (CTA)

    ---

    КОНТЕКСТ:

    user_input: {user_input}

    client_profile: {client_profile}

    conversation_summary: {conversation_summary}

    recent_history: {recent_history}

    kb_context:
    {kb_context}

    kb_top_score: {kb_top_score:.3f}
    kb_count: {kb_count}

    ---

    ФОРМАТ ОТВЕТА (JSON):

    {{
    "decision": "RESPOND_KB | RESPOND_TEMPLATE | LLM_GENERATE | CALL_TOOL | ESCALATE_TO_HUMAN",
    "response": "string",
    "tool": "string|null",
    "tool_args": {{}},
    "requires_human": true|false,
    "confidence": 0.0
    }}

    ---

    ПРИМЕР:

    Вопрос: "Сколько стоит?"

    Если в KB есть цена:
    → RESPOND_KB + короткий ответ с CTA

    Ответ:
    {{
    "decision": "RESPOND_KB",
    "response": "Подключение стоит 5000 ₽ разово. Это закрывает первые диалоги с клиентами и не даёт терять заявки. Хочешь — покажу, как это будет работать у тебя.",
    "tool": null,
    "tool_args": {{}},
    "requires_human": false,
    "confidence": 0.9
    }}

    ---

    Возвращай только JSON.
    """
    ).strip()