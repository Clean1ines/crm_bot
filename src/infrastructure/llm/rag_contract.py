"""Typed contracts for the RAG search pipeline.

This module intentionally contains no Groq, DB, Redis, or FastAPI imports.
It defines the testable contract between:
- repository search
- optional query expansion
- deduplication
- deterministic reranking
- tool-facing result formatting
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Protocol


RAG_CANDIDATE_KNOWN_KEYS = frozenset(
    {
        "id",
        "content",
        "score",
        "method",
        "source",
        "title",
        "chunk_index",
    }
)


@dataclass(frozen=True, slots=True)
class RAGPipelineConfig:
    """Runtime limits and scoring knobs for RAG search."""

    limit_per_query: int = 10
    final_limit: int = 3
    max_expansions: int = 3
    max_candidates: int = 60
    keyword_boost: float = 0.15
    position_boost: float = 0.05

    def normalized(self) -> "RAGPipelineConfig":
        return RAGPipelineConfig(
            limit_per_query=max(1, min(int(self.limit_per_query), 50)),
            final_limit=max(1, min(int(self.final_limit), 20)),
            max_expansions=max(0, min(int(self.max_expansions), 10)),
            max_candidates=max(1, min(int(self.max_candidates), 200)),
            keyword_boost=max(0.0, float(self.keyword_boost)),
            position_boost=max(0.0, float(self.position_boost)),
        )


@dataclass(slots=True)
class RAGCandidate:
    """Normalized candidate returned by repository search."""

    id: str
    content: str
    score: float = 0.0
    method: str = "unknown"
    source: str | None = None
    title: str | None = None
    chunk_index: int | None = None
    metadata: dict[str, object] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> "RAGCandidate":
        return cls(
            id=_to_text(payload.get("id"), default=""),
            content=_to_text(payload.get("content"), default=""),
            score=_to_float(payload.get("score"), default=0.0),
            method=_to_text(payload.get("method"), default="unknown"),
            source=_to_optional_text(payload.get("source")),
            title=_to_optional_text(payload.get("title")),
            chunk_index=_to_optional_int(payload.get("chunk_index")),
            metadata=_metadata_without_known_keys(payload),
        )

    def to_tool_payload(self) -> dict[str, object]:
        return {
            "id": self.id,
            "content": self.content,
            "score": self.score,
            "method": self.method,
            "source": self.source,
            "title": self.title,
            "chunk_index": self.chunk_index,
        }


def _to_text(value: object, *, default: str) -> str:
    if value is None:
        return default

    text = str(value)
    return text or default


def _to_optional_text(value: object) -> str | None:
    if value is None:
        return None

    return str(value)


def _to_float(value: object, *, default: float) -> float:
    try:
        return float(value or default)
    except (TypeError, ValueError):
        return default


def _to_optional_int(value: object) -> int | None:
    if value is None:
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _metadata_without_known_keys(payload: Mapping[str, object]) -> dict[str, object]:
    return {
        key: value
        for key, value in payload.items()
        if key not in RAG_CANDIDATE_KNOWN_KEYS
    }


class QueryExpander(Protocol):
    """Optional query expansion port.

    Production may use Groq.
    Tests can use a deterministic fake.
    """

    async def expand(self, query: str, *, max_expansions: int) -> list[str]:
        ...


class KnowledgeSearchRepository(Protocol):
    """Repository port used by RAGService."""

    async def search(
        self,
        project_id: str,
        query: str,
        limit: int = 10,
        hybrid_fallback: bool = True,
    ) -> list[Mapping[str, object]]:
        ...
