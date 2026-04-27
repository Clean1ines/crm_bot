"""
Functions for building prompts for graph nodes.
"""

import json
from pathlib import Path
from typing import Sequence

from src.agent.router.utils import compact_whitespace, extract_kb_text, truncate_text
from src.domain.runtime.prompting import (
    NO_DATA_TEXT,
    NO_KNOWLEDGE_TEXT,
    ProjectPromptContext,
)
from src.domain.runtime.state_contracts import (
    HistoryMessage,
    ProjectRuntimeConfigurationState,
)
from src.infrastructure.config.settings import settings
from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)

DEFAULT_KB_THRESHOLD = float(
    getattr(settings, "ROUTER_KB_THRESHOLD", getattr(settings, "KB_THRESHOLD", 0.78))
)
DEFAULT_LLM_THRESHOLD = float(
    getattr(settings, "ROUTER_LLM_THRESHOLD", getattr(settings, "LLM_THRESHOLD", 0.70))
)
DEFAULT_KB_LIMIT = int(getattr(settings, "ROUTER_KB_LIMIT", 5))

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

_intent_prompt_template: str | None = None
_response_prompt_template: str | None = None
_interpretation_block: str | None = None


def _load_prompt_template(filename: str) -> str:
    filepath = PROMPTS_DIR / filename
    try:
        return filepath.read_text(encoding="utf-8")
    except Exception as exc:
        logger.error(
            "Failed to load prompt template",
            extra={"file": filename, "error": str(exc)},
        )
        return ""


def format_kb_results(
    kb_results: Sequence[object], limit: int = DEFAULT_KB_LIMIT
) -> tuple[str, float, int]:
    if not kb_results:
        return "[]", 0.0, 0

    lines: list[str] = []
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
            text = extract_kb_text(item)

        top_score = max(top_score, score)
        parts: list[str] = [f"{index}. score={score:.3f}"]
        if question:
            parts.append(f"question={question}")
        if method:
            parts.append(f"method={method}")
        if text:
            parts.append(f"text={truncate_text(text, 420)}")
        lines.append(" | ".join(parts))

    return "\n".join(lines), top_score, len(lines)


def format_history(history: Sequence[object], limit: int = 5) -> str:
    if not history:
        return "[]"

    lines: list[str] = []
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
    kb_count: int, top_score: float, question_count: int, kb_threshold: float
) -> str:
    if kb_count <= 0:
        return "LLM_ONLY"
    if top_score >= kb_threshold and question_count <= 1:
        return "DIRECT_KB"
    if question_count >= 2 or kb_count >= 2:
        return "HYBRID_SYNTHESIS"
    return "KB_AUGMENTED_LLM"


def _format_memory(memory_by_type: dict[str, list[dict[str, object]]]) -> str:
    if not memory_by_type:
        return ""

    lines: list[str] = []
    for memory_type, items in memory_by_type.items():
        lines.append(f"--- {memory_type.upper()} ---")
        for item in items:
            key = item.get("key", "?")
            value = item.get("value")
            value_text = (
                json.dumps(value, ensure_ascii=False)
                if isinstance(value, dict)
                else str(value)
            )
            lines.append(f"  {key}: {truncate_text(value_text, 200)}")
    return "\n".join(lines)


def _format_features(features: dict[str, float] | None) -> str:
    if not features:
        return NO_DATA_TEXT
    return ", ".join(
        f"{name} (interest: {score:.1f})" for name, score in features.items()
    )


def format_project_configuration(
    project_configuration: dict[str, object] | None,
) -> str:
    context = ProjectPromptContext.from_configuration(project_configuration)
    lines = context.format_lines(truncate=truncate_text)
    return "\n".join(lines) if lines else NO_DATA_TEXT


def build_intent_prompt(
    user_input: str,
    conversation_summary: str | None = None,
    history: list[HistoryMessage] | None = None,
    user_memory: dict[str, list[dict[str, object]]] | None = None,
) -> str:
    global _intent_prompt_template
    if _intent_prompt_template is None:
        _intent_prompt_template = _load_prompt_template("intent_prompt.txt")

    hist_str = format_history(history, limit=5) if history else "[]"
    mem_str = _format_memory(user_memory) if user_memory else ""
    return _intent_prompt_template.format(
        user_input=user_input,
        conversation_summary=conversation_summary or NO_DATA_TEXT,
        history=hist_str,
        user_memory=mem_str or NO_DATA_TEXT,
    )


def build_response_prompt(
    decision: str,
    features: dict[str, float] | None = None,
    user_input: str = "",
    conversation_summary: str | None = None,
    history: list[HistoryMessage] | None = None,
    user_memory: dict[str, list[dict[str, object]]] | None = None,
    knowledge_chunks: Sequence[object] | None = None,
    project_configuration: ProjectRuntimeConfigurationState | None = None,
) -> str:
    global _response_prompt_template, _interpretation_block
    if _response_prompt_template is None:
        _response_prompt_template = _load_prompt_template("response_prompt.txt")
    if _interpretation_block is None:
        _interpretation_block = _load_prompt_template("interpretation_block.txt")

    hist_str = format_history(history, limit=5) if history else "[]"
    mem_str = _format_memory(user_memory) if user_memory else ""
    feat_str = _format_features(features)
    project_context = format_project_configuration(project_configuration)
    knowledge_block = (
        format_kb_results(knowledge_chunks, limit=DEFAULT_KB_LIMIT)[0]
        if knowledge_chunks
        else NO_KNOWLEDGE_TEXT
    )

    return _response_prompt_template.format(
        decision=decision,
        features=feat_str,
        user_input=user_input,
        conversation_summary=conversation_summary or NO_DATA_TEXT,
        history=hist_str,
        user_memory=mem_str or NO_DATA_TEXT,
        project_context=project_context,
        knowledge_block=knowledge_block,
        interpretation_block=_interpretation_block,
    )
