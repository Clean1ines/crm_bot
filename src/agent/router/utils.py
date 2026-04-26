"""
Prompt formatting helpers for agent runtime nodes.

This module is intentionally an agent-layer helper. It does not define domain
routing policy and does not parse router LLM outputs. Current runtime routing is
implemented by explicit graph nodes: intent extraction, policy engine, KB search,
tool execution, escalation, response generation, responder, and persist.
"""

import json
import re
from typing import Any


def compact_whitespace(text: str) -> str:
    """
    Normalize whitespace so prompt contexts stay compact and cheap.
    """
    return re.sub(r"\s+", " ", text or "").strip()


def truncate_text(text: str, max_length: int = 280) -> str:
    """
    Truncate text to a safe prompt size while keeping it readable.
    """
    normalized = compact_whitespace(text)
    if len(normalized) <= max_length:
        return normalized
    return normalized[: max_length - 1].rstrip() + "…"


def safe_json_dumps(value: Any, *, indent: int = 2) -> str:
    """
    Serialize values to JSON safely for prompt/debug usage.
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
    """
    if isinstance(item, str):
        return compact_whitespace(item)

    if isinstance(item, dict):
        for key in ("answer", "content", "text", "snippet", "reply"):
            value = item.get(key)
            if value:
                return compact_whitespace(str(value))
    return ""
