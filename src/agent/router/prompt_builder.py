"""
Functions for building prompts for graph nodes.
"""

import json
from pathlib import Path
from typing import Mapping, Sequence, cast

from src.agent.router.utils import compact_whitespace, extract_kb_text, truncate_text
from src.domain.runtime.prompting import (
    NO_DATA_TEXT,
    NO_KNOWLEDGE_TEXT,
    ProjectPromptContext,
    TruncateText,
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


COMMERCIAL_CONTEXT_USEFUL_STATUSES = {
    "answerable",
    "needs_clarification",
    "requires_manager",
    "conflict",
}


def format_commercial_context(
    commercial_context: Mapping[str, object] | None,
) -> str:
    if not commercial_context:
        return ""

    decision = str(commercial_context.get("decision") or "").strip()
    if decision not in COMMERCIAL_CONTEXT_USEFUL_STATUSES:
        return ""

    lines: list[str] = [
        "STRUCTURED COMMERCIAL CONTEXT — priority over generic KB when relevant.",
        f"decision={decision}",
    ]

    missing_slots = commercial_context.get("missing_slots")
    if isinstance(missing_slots, list) and missing_slots:
        lines.append(
            "missing_slots="
            + ", ".join(truncate_text(str(slot), 80) for slot in missing_slots)
        )

    manager_reason = commercial_context.get("manager_reason")
    if manager_reason:
        lines.append(f"manager_reason={truncate_text(str(manager_reason), 160)}")

    conflict_reason = commercial_context.get("conflict_reason")
    if conflict_reason:
        lines.append(f"conflict_reason={truncate_text(str(conflict_reason), 160)}")

    raw_facts = commercial_context.get("facts")
    if isinstance(raw_facts, list):
        formatted_facts = [
            _format_commercial_fact(raw_fact)
            for raw_fact in raw_facts[:3]
            if isinstance(raw_fact, Mapping)
        ]
        if formatted_facts:
            lines.append("facts:")
            lines.extend(formatted_facts)

    lines.append(
        "Instruction: use this structured commercial context first for prices. "
        "If decision=needs_clarification, ask only for the missing variant. "
        "If decision=requires_manager, explain that a manager should confirm the price."
    )
    return "\n".join(lines)


def _format_commercial_fact(raw_fact: Mapping[str, object]) -> str:
    item_name = truncate_text(str(raw_fact.get("item_name") or "unknown"), 120)
    value_kind = truncate_text(str(raw_fact.get("value_kind") or "unknown"), 80)
    unit = truncate_text(str(raw_fact.get("unit") or ""), 80)
    price_text = _commercial_fact_price_text(raw_fact)
    source_text = _commercial_fact_source_text(raw_fact)
    variant_text = _commercial_fact_variant_text(raw_fact)

    parts = [
        f"- item={item_name}",
        f"value_kind={value_kind}",
    ]
    if price_text:
        parts.append(f"price={price_text}")
    if unit:
        parts.append(f"unit={unit}")
    if variant_text:
        parts.append(f"variant={variant_text}")
    if source_text:
        parts.append(f"source={source_text}")

    return " | ".join(parts)


def _commercial_fact_price_text(raw_fact: Mapping[str, object]) -> str:
    amount = raw_fact.get("amount")
    if isinstance(amount, Mapping):
        raw_amount = amount.get("amount")
        currency = amount.get("currency")
        if raw_amount is not None and currency is not None:
            return truncate_text(f"{raw_amount} {currency}", 120)

    price_range = raw_fact.get("price_range")
    if isinstance(price_range, Mapping):
        min_amount = price_range.get("min_amount")
        max_amount = price_range.get("max_amount")
        if isinstance(min_amount, Mapping) and isinstance(max_amount, Mapping):
            return truncate_text(
                f"{min_amount.get('amount')} {min_amount.get('currency')} - "
                f"{max_amount.get('amount')} {max_amount.get('currency')}",
                160,
            )

    price_text = raw_fact.get("price_text")
    return truncate_text(str(price_text), 160) if price_text else ""


def _commercial_fact_source_text(raw_fact: Mapping[str, object]) -> str:
    source_refs = raw_fact.get("source_refs")
    if not isinstance(source_refs, list) or not source_refs:
        return ""

    first_ref = source_refs[0]
    if not isinstance(first_ref, Mapping):
        return ""

    quote = first_ref.get("quote")
    return truncate_text(str(quote), 180) if quote else ""


def _commercial_fact_variant_text(raw_fact: Mapping[str, object]) -> str:
    variant = raw_fact.get("variant")
    if not isinstance(variant, Mapping) or not variant:
        return ""

    items = [
        f"{truncate_text(str(key), 60)}={truncate_text(str(value), 80)}"
        for key, value in variant.items()
    ]
    return ", ".join(items)


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
    commercial_context: Mapping[str, object] | None = None,
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
    commercial_context_block = format_commercial_context(commercial_context)
    knowledge_block = (
        f"{commercial_context_block}\n\nGENERIC KNOWLEDGE BASE:\n{kb_block}"
        if commercial_context_block
        else kb_block
    )

    return response_prompt_template.format(
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
