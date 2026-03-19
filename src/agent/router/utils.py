"""
Utility functions for the router node: text normalization, keyword detection,
model ID extraction, etc.
"""

import re
import json
from typing import Any, Optional, Sequence

from src.core.config import settings
from src.core.logging import get_logger

logger = get_logger(__name__)

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


def compact_whitespace(text: str) -> str:
    """
    Normalize whitespace so prompt contexts stay compact and cheap.

    Args:
        text: Arbitrary text.

    Returns:
        Text with consecutive whitespace collapsed into single spaces.
    """
    return re.sub(r"\s+", " ", text or "").strip()


def truncate_text(text: str, max_length: int = 280) -> str:
    """
    Truncate text to a safe prompt size while keeping it readable.

    Args:
        text: Input text.
        max_length: Maximum allowed length.

    Returns:
        Truncated text with ellipsis if needed.
    """
    normalized = compact_whitespace(text)
    if len(normalized) <= max_length:
        return normalized
    return normalized[: max_length - 1].rstrip() + "…"


def safe_json_dumps(value: Any, *, indent: int = 2) -> str:
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


def extract_kb_text(item: Any) -> str:
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
        return compact_whitespace(item)

    if isinstance(item, dict):
        for key in ("answer", "content", "text", "snippet", "reply"):
            value = item.get(key)
            if value:
                return compact_whitespace(str(value))
    return ""


def count_question_signals(text: str) -> int:
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


def has_sensitive_or_urgent_intent(text: str) -> bool:
    """
    Detect sensitive or urgent intent that should bias toward a stronger model.

    Args:
        text: User message.

    Returns:
        True if the message contains sensitive or urgent intent.
    """
    lowered = (text or "").lower()
    return any(keyword in lowered for keyword in SENSITIVE_KEYWORDS)


def has_complex_intent(text: str) -> bool:
    """
    Detect requests that typically benefit from a larger model.

    Args:
        text: User message.

    Returns:
        True if the message likely needs stronger reasoning.
    """
    lowered = (text or "").lower()
    return any(keyword in lowered for keyword in COMPLEXITY_KEYWORDS)


def extract_model_id(candidate: Any) -> str:
    """
    Extract a model identifier from a registry item (dict) or from a raw string.

    Args:
        candidate: Registry entry returned by ModelRegistry, or a string.

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
