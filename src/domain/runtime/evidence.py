from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum


class EvidenceSourceType(StrEnum):
    """Answer-time evidence source categories.

    These are runtime evidence categories, not persistence table names.
    """

    COMPILED_KNOWLEDGE = "compiled_knowledge"
    COMPILED_PRICE_LIST = "compiled_price_list"
    CRM_OPERATIONAL = "crm_operational"
    CATALOG_OPERATIONAL = "catalog_operational"
    CONVERSATION_MEMORY = "conversation_memory"
    USER_MESSAGE = "user_message"
    MANAGER_OVERRIDE = "manager_override"
    TOOL_RESULT = "tool_result"
    LLM_REASONING = "llm_reasoning"


class EvidenceFreshness(StrEnum):
    LIVE = "live"
    CURRENT = "current"
    SNAPSHOT = "snapshot"
    STALE = "stale"
    UNKNOWN = "unknown"


class EvidenceScope(StrEnum):
    PROJECT = "project"
    CUSTOMER = "customer"
    THREAD = "thread"
    DOCUMENT = "document"
    EXTERNAL = "external"
    SYSTEM = "system"


_NON_AUTHORITATIVE_SOURCE_TYPES = frozenset(
    {
        EvidenceSourceType.LLM_REASONING,
    }
)


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    """A single answer-time fact with provenance.

    The content may be rendered to the LLM, but source_type/scope/freshness are
    what domain/application policy should use to decide authority.
    """

    source_type: EvidenceSourceType
    content: str
    scope: EvidenceScope
    source_id: str | None = None
    fact_key: str | None = None
    freshness: EvidenceFreshness = EvidenceFreshness.UNKNOWN
    confidence: float = 1.0
    payload: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.content.strip():
            raise ValueError("evidence content must not be empty")
        if self.confidence < 0.0 or self.confidence > 1.0:
            raise ValueError("evidence confidence must be between 0 and 1")

    @property
    def is_authoritative(self) -> bool:
        return self.source_type not in _NON_AUTHORITATIVE_SOURCE_TYPES

    @property
    def normalized_fact_key(self) -> str | None:
        if self.fact_key is None:
            return None
        normalized = " ".join(self.fact_key.strip().lower().split())
        return normalized or None


@dataclass(frozen=True, slots=True)
class EvidenceBundle:
    """Evidence collected for one answer attempt."""

    items: tuple[EvidenceItem, ...] = ()

    @classmethod
    def from_items(cls, items: Sequence[EvidenceItem]) -> "EvidenceBundle":
        return cls(items=tuple(items))

    @property
    def is_empty(self) -> bool:
        return not self.items

    def authoritative_items(self) -> tuple[EvidenceItem, ...]:
        return tuple(item for item in self.items if item.is_authoritative)

    def by_source_type(
        self,
        source_type: EvidenceSourceType,
    ) -> tuple[EvidenceItem, ...]:
        return tuple(item for item in self.items if item.source_type == source_type)

    def by_fact_key(self, fact_key: str) -> tuple[EvidenceItem, ...]:
        normalized = " ".join(fact_key.strip().lower().split())
        return tuple(
            item for item in self.items if item.normalized_fact_key == normalized
        )

    def fact_keys(self) -> tuple[str, ...]:
        keys: list[str] = []
        for item in self.items:
            key = item.normalized_fact_key
            if key and key not in keys:
                keys.append(key)
        return tuple(keys)

    def without_llm_reasoning(self) -> "EvidenceBundle":
        return EvidenceBundle(
            items=tuple(
                item
                for item in self.items
                if item.source_type != EvidenceSourceType.LLM_REASONING
            )
        )
