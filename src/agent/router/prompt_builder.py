"""
Functions for building prompts for graph nodes.
"""

import json
from pathlib import Path
from typing import Sequence, cast

from src.agent.router.utils import compact_whitespace, extract_kb_text, truncate_text
from src.domain.runtime.prompting import (
    NO_DATA_TEXT,
    NO_KNOWLEDGE_TEXT,
    ProjectPromptContext,
    TruncateText,
)
from src.domain.runtime.evidence_references import EvidenceReferenceIndex
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
_response_prompt_templates: dict[str, str] = {}
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

    evidence_index = EvidenceReferenceIndex.from_knowledge_chunks(
        kb_results,
        limit=limit,
    )
    lines: list[str] = []
    top_score = 0.0
    for item in kb_results:
        score = 0.0
        text = ""
        method = ""
        entry_id = ""

        if isinstance(item, dict):
            entry_id = compact_whitespace(str(item.get("id", "")))
            evidence_ref = evidence_index.entry_id_to_alias.get(entry_id)
            if evidence_ref is None:
                continue
            raw_score = item.get("score", 0.0)
            try:
                score = float(raw_score or 0.0)
            except (TypeError, ValueError):
                score = 0.0

            text = extract_kb_text(item)
            method = compact_whitespace(str(item.get("method", "")))
        else:
            continue

        top_score = max(top_score, score)
        parts: list[str] = [f"{evidence_ref} | score={score:.3f}"]
        if method:
            parts.append(f"method={method}")
        if text:
            parts.append(f"text={truncate_text(text, 420)}")
        lines.append(" | ".join(parts))

    return "\n".join(lines), top_score, len(lines)


def format_kb_prompt_entry_traces(
    kb_results: Sequence[object],
    limit: int = DEFAULT_KB_LIMIT,
) -> list[dict[str, object]]:
    evidence_index = EvidenceReferenceIndex.from_knowledge_chunks(
        kb_results,
        limit=limit,
    )
    entries: list[dict[str, object]] = []
    for item in kb_results:
        entry_id = None
        score = 0.0
        text = extract_kb_text(item)
        if isinstance(item, dict):
            entry_id = item.get("id")
            evidence_ref = evidence_index.entry_id_to_alias.get(str(entry_id or ""))
            if evidence_ref is None:
                continue
            raw_score = item.get("score", 0.0)
            try:
                score = float(raw_score or 0.0)
            except (TypeError, ValueError):
                score = 0.0
        else:
            continue

        prompt_text = truncate_text(text, 420) if text else ""
        entries.append(
            {
                "rank": len(entries) + 1,
                "evidence_ref": evidence_ref,
                "canonical_entry_id": entry_id,
                "score": score,
                "content_preview": truncate_text(prompt_text, 160),
                "content_chars_before_truncation": len(text),
                "content_chars_in_prompt": len(prompt_text),
                "was_truncated": len(prompt_text) < len(text),
            }
        )
    return entries


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

    ordered_types = (
        "preferences",
        "rejections",
        "behavior",
        "issues",
        "context",
        "agreements",
        "profile",
        "dialog_state",
    )
    type_order = {memory_type: index for index, memory_type in enumerate(ordered_types)}
    lines: list[str] = []
    for memory_type, items in sorted(
        memory_by_type.items(),
        key=lambda item: (type_order.get(item[0], len(type_order)), item[0]),
    ):
        formatted_items = _format_memory_items(memory_type, items[:3])
        if formatted_items:
            lines.append(f"- {memory_type}: {'; '.join(formatted_items)}")
    return "\n".join(lines)


def _format_memory_items(
    memory_type: str,
    items: list[dict[str, object]],
) -> list[str]:
    if memory_type == "dialog_state":
        return _format_dialog_state_memory(items)

    formatted: list[str] = []
    for item in items:
        key = str(item.get("key") or "?")
        value_text = _memory_value_text(item.get("value"))
        if value_text:
            formatted.append(f"{key}={value_text}")
    return formatted


def _format_dialog_state_memory(items: list[dict[str, object]]) -> list[str]:
    for item in items:
        value = item.get("value")
        if not isinstance(value, dict):
            continue

        fields = (
            ("lifecycle", value.get("lifecycle")),
            ("lead_status", value.get("lead_status")),
            ("last_topic", value.get("last_topic")),
            ("last_intent", value.get("last_intent")),
            ("repeat_count", value.get("repeat_count")),
        )
        formatted = [
            f"{key}={truncate_text(str(field_value), 80)}"
            for key, field_value in fields
            if field_value not in {None, ""}
        ]
        if formatted:
            return formatted
    return []


def _memory_value_text(value: object) -> str:
    if isinstance(value, dict):
        return truncate_text(
            json.dumps(value, ensure_ascii=False, separators=(",", ":")),
            160,
        )
    return truncate_text(str(value), 160)


def _format_features(features: dict[str, float] | None) -> str:
    if not features:
        return NO_DATA_TEXT
    return ", ".join(
        f"{name} (interest: {score:.1f})" for name, score in features.items()
    )


def _prompt_configuration_state(
    value: ProjectRuntimeConfigurationState | dict[str, object] | None,
) -> ProjectRuntimeConfigurationState | None:
    if value is None:
        return None
    return cast(ProjectRuntimeConfigurationState, value)


def _truncate_project_prompt_text(value: str, limit: int) -> str:
    return truncate_text(value, limit)


PROJECT_PROMPT_TRUNCATE: TruncateText = _truncate_project_prompt_text


def format_project_configuration(
    project_configuration: dict[str, object] | None,
) -> str:
    context = ProjectPromptContext.from_configuration(
        _prompt_configuration_state(project_configuration)
    )
    lines = context.format_lines(truncate=PROJECT_PROMPT_TRUNCATE)
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
    generation_mode: str = "KNOWLEDGE_ANSWER",
    tool_result: object | None = None,
    project_configuration: ProjectRuntimeConfigurationState | None = None,
    target_language: str | None = None,
) -> str:
    global _response_prompt_templates, _response_prompt_template, _interpretation_block
    lang = (target_language or "").strip().lower()
    template_key = lang if lang in {"ru", "en", "de", "es"} else "default"
    if template_key not in _response_prompt_templates:
        localized_name = (
            f"response_prompt.{template_key}.txt"
            if template_key != "default"
            else "response_prompt.txt"
        )
        template = _load_prompt_template(localized_name)
        if not template:
            template = _load_prompt_template("response_prompt.txt")
        _response_prompt_templates[template_key] = template
    response_prompt_template = _response_prompt_templates[template_key]
    _response_prompt_template = response_prompt_template
    if _interpretation_block is None:
        _interpretation_block = _load_prompt_template("interpretation_block.txt")

    hist_str = format_history(history, limit=5) if history else "[]"
    mem_str = _format_memory(user_memory) if user_memory else ""
    feat_str = _format_features(features)
    project_context = format_project_configuration(
        cast(dict[str, object] | None, project_configuration)
    )
    kb_block = (
        format_kb_results(knowledge_chunks, limit=DEFAULT_KB_LIMIT)[0]
        if knowledge_chunks
        else NO_KNOWLEDGE_TEXT
    )
    knowledge_block = kb_block
    tool_result_block = (
        truncate_text(
            json.dumps(tool_result, ensure_ascii=False, separators=(",", ":")),
            1200,
        )
        if tool_result is not None
        else NO_DATA_TEXT
    )

    return response_prompt_template.format(
        decision=decision,
        generation_mode=generation_mode,
        features=feat_str,
        user_input=user_input,
        conversation_summary=conversation_summary or NO_DATA_TEXT,
        history=hist_str,
        user_memory=mem_str or NO_DATA_TEXT,
        project_context=project_context,
        knowledge_block=knowledge_block,
        tool_result=tool_result_block,
        interpretation_block=_interpretation_block,
    )
