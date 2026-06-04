from __future__ import annotations

from typing import Literal, TypeAlias


MODE_FAQ: Literal["faq"] = "faq"
MODE_PRICE_LIST: Literal["price_list"] = "price_list"

KnowledgeProcessingMode: TypeAlias = Literal["faq", "price_list"]


class KnowledgeProcessingModeValidationError(ValueError):
    """Raised when a knowledge processing mode is not supported by current code."""


def normalize_knowledge_processing_mode(value: object) -> KnowledgeProcessingMode:
    raw = str(value or MODE_FAQ).strip().lower().replace("-", "_")

    if raw in {"", MODE_FAQ, "faq_workbench", "faq_section_registry_v1"}:
        return MODE_FAQ
    if raw in {MODE_PRICE_LIST, "price", "prices", "commercial_price"}:
        return MODE_PRICE_LIST

    raise KnowledgeProcessingModeValidationError(
        f"Unsupported knowledge processing mode: {value!r}"
    )


def require_faq_workbench_mode(value: object) -> KnowledgeProcessingMode:
    mode = normalize_knowledge_processing_mode(value)
    if mode != MODE_FAQ:
        raise KnowledgeProcessingModeValidationError(
            "Only FAQ Workbench uploads are supported by this boundary."
        )
    return mode


__all__ = [
    "MODE_FAQ",
    "MODE_PRICE_LIST",
    "KnowledgeProcessingMode",
    "KnowledgeProcessingModeValidationError",
    "normalize_knowledge_processing_mode",
    "require_faq_workbench_mode",
]
