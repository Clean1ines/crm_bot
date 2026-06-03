from __future__ import annotations

from enum import StrEnum


class KnowledgeEntryKind(StrEnum):
    ANSWER = "answer"
    FAQ_ANSWER = "faq_answer"
    CONTACT_INFO = "contact_info"
    WORKING_HOURS = "working_hours"
    CATALOG_ANSWER = "catalog_answer"
    PRICE_ANSWER = "price_answer"
    PRICING_POLICY = "pricing_policy"
    REFUND_POLICY = "refund_policy"
    DELIVERY_POLICY = "delivery_policy"
    POLICY_CLAUSE = "policy_clause"
    PROCEDURE = "procedure"
    WARNING = "warning"
    REQUIREMENT = "requirement"
    TROUBLESHOOTING_STEP = "troubleshooting_step"
    CUSTOM = "custom"
    FALLBACK_CHUNK = "fallback_chunk"


RUNTIME_ENTRY_KIND_VALUES: frozenset[str] = frozenset(
    {
        KnowledgeEntryKind.ANSWER.value,
        KnowledgeEntryKind.CATALOG_ANSWER.value,
        KnowledgeEntryKind.CONTACT_INFO.value,
        KnowledgeEntryKind.CUSTOM.value,
        KnowledgeEntryKind.DELIVERY_POLICY.value,
        KnowledgeEntryKind.FAQ_ANSWER.value,
        KnowledgeEntryKind.POLICY_CLAUSE.value,
        KnowledgeEntryKind.PRICE_ANSWER.value,
        KnowledgeEntryKind.PRICING_POLICY.value,
        KnowledgeEntryKind.PROCEDURE.value,
        KnowledgeEntryKind.REFUND_POLICY.value,
        KnowledgeEntryKind.REQUIREMENT.value,
        KnowledgeEntryKind.TROUBLESHOOTING_STEP.value,
        KnowledgeEntryKind.WARNING.value,
        KnowledgeEntryKind.WORKING_HOURS.value,
    }
)

__all__ = [
    "KnowledgeEntryKind",
    "RUNTIME_ENTRY_KIND_VALUES",
]
