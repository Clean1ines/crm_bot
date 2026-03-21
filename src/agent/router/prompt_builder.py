"""
Functions for building prompts for various nodes.
"""

import json
from pathlib import Path
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

# Path to prompts directory
PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

# Cache for prompt templates
_intent_prompt_template = None
_response_prompt_template = None
_interpretation_block = None


def _load_prompt_template(filename: str) -> str:
    """Load prompt template from file."""
    filepath = PROMPTS_DIR / filename
    try:
        return filepath.read_text(encoding="utf-8")
    except Exception as e:
        logger.error("Failed to load prompt template", extra={"file": filename, "error": str(e)})
        return ""


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


def _format_features(features: Optional[Dict[str, float]]) -> str:
    """Format features dict into readable string."""
    if not features:
        return "нет упоминаний"
    items = []
    for name, score in features.items():
        items.append(f"{name} (интерес: {score:.1f})")
    return ", ".join(items)


def build_intent_prompt(
    user_input: str,
    conversation_summary: Optional[str] = None,
    history: Optional[List[Dict]] = None,
    user_memory: Optional[Dict[str, List[Dict]]] = None,
) -> str:
    """
    Build prompt for intent extraction.

    Args:
        user_input: Current user message.
        conversation_summary: Optional summary of previous conversation.
        history: Optional list of recent messages.
        user_memory: Optional user memory.

    Returns:
        Formatted prompt string.
    """
    global _intent_prompt_template
    if _intent_prompt_template is None:
        _intent_prompt_template = _load_prompt_template("intent_prompt.txt")

    # Format history if provided
    hist_str = format_history(history, limit=5) if history else "[]"
    # Format memory if provided
    mem_str = _format_memory(user_memory) if user_memory else ""

    return _intent_prompt_template.format(
        user_input=user_input,
        conversation_summary=conversation_summary or "нет",
        history=hist_str,
        user_memory=mem_str or "нет"
    )


def build_response_prompt(
    decision: str,
    features: Optional[Dict[str, float]] = None,
    user_input: str = "",
    conversation_summary: Optional[str] = None,
    history: Optional[List[Dict]] = None,
    user_memory: Optional[Dict[str, List[Dict]]] = None,
    knowledge_chunks: Optional[Sequence[Any]] = None,
) -> str:
    """
    Build prompt for response generation.

    Args:
        decision: Decision from policy engine (e.g., "LLM_GENERATE").
        features: Extracted features with interest scores.
        user_input: Current user message.
        conversation_summary: Optional summary of previous conversation.
        history: Optional list of recent messages.
        user_memory: Optional user memory.
        knowledge_chunks: Optional list of knowledge base chunks.

    Returns:
        Formatted prompt string.
    """
    global _response_prompt_template, _interpretation_block
    if _response_prompt_template is None:
        _response_prompt_template = _load_prompt_template("response_prompt.txt")
    if _interpretation_block is None:
        _interpretation_block = _load_prompt_template("interpretation_block.txt")

    # Format history
    hist_str = format_history(history, limit=5) if history else "[]"
    # Format memory
    mem_str = _format_memory(user_memory) if user_memory else ""
    # Format features
    feat_str = _format_features(features)

    # Format knowledge chunks if provided
    if knowledge_chunks:
        knowledge_block, _, _ = format_kb_results(knowledge_chunks, limit=DEFAULT_KB_LIMIT)
    else:
        knowledge_block = "Нет данных из базы знаний."

    return _response_prompt_template.format(
        decision=decision,
        features=feat_str,
        user_input=user_input,
        conversation_summary=conversation_summary or "нет",
        history=hist_str,
        user_memory=mem_str or "нет",
        knowledge_block=knowledge_block,
        interpretation_block=_interpretation_block
    )
