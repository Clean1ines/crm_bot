from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import hashlib
from typing import cast

from src.domain.runtime.state_contracts import RuntimeStateInput


def hash_commercial_context_query(query: str) -> str:
    return hashlib.md5(query.encode("utf-8"), usedforsecurity=False).hexdigest()


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


@dataclass(slots=True)
class CommercialContextLookupContext:
    project_id: str | None
    thread_id: str | None = None
    query: str = ""

    @classmethod
    def from_state(
        cls,
        state: RuntimeStateInput,
    ) -> "CommercialContextLookupContext":
        return cls(
            project_id=_optional_text(state.get("project_id")),
            thread_id=_optional_text(state.get("thread_id")),
            query=str(state.get("user_input") or ""),
        )

    @property
    def query_hash(self) -> str:
        return hash_commercial_context_query(self.query)


@dataclass(slots=True)
class CommercialContextLookupResult:
    status: str
    context: Mapping[str, object] = field(default_factory=dict)
    sources: tuple[Mapping[str, object], ...] = ()

    @classmethod
    def skipped(cls, reason: str) -> "CommercialContextLookupResult":
        return cls(
            status="skipped",
            context={"decision": "skipped", "reason": reason},
        )

    @classmethod
    def error(cls, reason: str) -> "CommercialContextLookupResult":
        return cls(
            status="error",
            context={"decision": "error", "reason": reason},
        )

    @classmethod
    def from_tool_payload(
        cls,
        payload: Mapping[str, object] | None,
    ) -> "CommercialContextLookupResult":
        if payload is None:
            return cls.skipped("empty_tool_payload")

        decision = str(payload.get("decision") or "not_found")
        return cls(
            status=decision,
            context=dict(payload),
            sources=_extract_source_refs(payload),
        )

    def to_state_patch(self) -> dict[str, object]:
        return {
            "commercial_context": dict(self.context),
            "commercial_context_status": self.status,
            "commercial_context_sources": [dict(source) for source in self.sources],
        }


def _extract_source_refs(
    payload: Mapping[str, object],
) -> tuple[Mapping[str, object], ...]:
    raw_facts = payload.get("facts")
    if not isinstance(raw_facts, list):
        return ()

    sources: list[Mapping[str, object]] = []
    for raw_fact in raw_facts:
        if not isinstance(raw_fact, Mapping):
            continue
        fact = cast(Mapping[str, object], raw_fact)
        raw_refs = fact.get("source_refs")
        if not isinstance(raw_refs, list):
            continue
        for raw_ref in raw_refs:
            if isinstance(raw_ref, Mapping):
                sources.append(cast(Mapping[str, object], raw_ref))

    return tuple(sources)
