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
from typing import Any, Mapping, Protocol


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
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "RAGCandidate":
        raw_score = payload.get("score", 0.0)
        try:
            score = float(raw_score or 0.0)
        except (TypeError, ValueError):
            score = 0.0

        chunk_index = payload.get("chunk_index")
        try:
            normalized_chunk_index = int(chunk_index) if chunk_index is not None else None
        except (TypeError, ValueError):
            normalized_chunk_index = None

        known_keys = {
            "id",
            "content",
            "score",
            "method",
            "source",
            "title",
            "chunk_index",
        }

        return cls(
            id=str(payload.get("id") or ""),
            content=str(payload.get("content") or ""),
            score=score,
            method=str(payload.get("method") or "unknown"),
            source=str(payload["source"]) if payload.get("source") is not None else None,
            title=str(payload["title"]) if payload.get("title") is not None else None,
            chunk_index=normalized_chunk_index,
            metadata={key: value for key, value in payload.items() if key not in known_keys},
        )

    def to_tool_payload(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "score": self.score,
            "method": self.method,
            "source": self.source,
            "title": self.title,
            "chunk_index": self.chunk_index,
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
    ) -> list[Mapping[str, Any]]:
        ...
