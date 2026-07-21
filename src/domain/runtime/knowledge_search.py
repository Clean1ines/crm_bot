from dataclasses import dataclass, field
from typing import Mapping, cast
import hashlib

from src.domain.runtime.cta import CONTINUE_EXPLANATION_CTA, normalize_cta
from src.domain.runtime.state_contracts import (
    KnowledgeChunkPayload,
    RuntimeStateInput,
    RuntimeStatePatch,
)
from src.domain.runtime.value_parsing import coerce_float


def hash_query(query: str) -> str:
    return hashlib.md5(query.encode("utf-8"), usedforsecurity=False).hexdigest()


@dataclass(slots=True)
class KnowledgeSearchContext:
    project_id: str | None
    thread_id: str | None = None
    query: str = ""
    original_user_input: str = ""

    @classmethod
    def from_state(cls, state: RuntimeStateInput) -> "KnowledgeSearchContext":
        original_user_input = str(state.get("user_input") or "")
        query = (
            _optional_text(state.get("knowledge_query"))
            if _can_use_resolved_query(state)
            else None
        ) or original_user_input
        return cls(
            project_id=state.get("project_id"),
            thread_id=state.get("thread_id"),
            query=query,
            original_user_input=original_user_input,
        )

    @property
    def query_hash(self) -> str:
        return hash_query(self.query)

    @property
    def original_user_input_hash(self) -> str:
        return hash_query(self.original_user_input)


@dataclass(slots=True)
class KnowledgeChunk:
    chunk_id: str
    score: float | None
    content: str
    method: str | None = None
    source: str | None = None
    title: str | None = None
    entry_kind: str | None = None
    document_id: str | None = None
    source_excerpt: str | None = None
    questions: object | None = None

    def to_prompt_payload(self) -> KnowledgeChunkPayload:
        return {
            "id": self.chunk_id,
            "score": self.score,
            "content": self.content,
        }


@dataclass(slots=True)
class KnowledgeSearchResult:
    chunks: list[KnowledgeChunk] = field(default_factory=list)

    @classmethod
    def from_tool_payload(
        cls, payload: Mapping[str, object] | None
    ) -> "KnowledgeSearchResult":
        raw_chunks = payload.get("results") if payload else []
        if not isinstance(raw_chunks, list):
            raw_chunks = []

        chunks: list[KnowledgeChunk] = []
        for index, item in enumerate(raw_chunks):
            if not isinstance(item, Mapping):
                continue
            row = cast(Mapping[str, object], item)
            chunks.append(
                KnowledgeChunk(
                    chunk_id=str(row.get("id", f"no-id-{index}")),
                    score=coerce_float(row.get("score")),
                    content=str(row.get("content") or ""),
                    method=_optional_text(row.get("method")),
                    source=_optional_text(row.get("source")),
                    title=_optional_text(row.get("title")),
                    entry_kind=_optional_text(row.get("entry_kind")),
                    document_id=_optional_text(row.get("document_id")),
                    source_excerpt=_optional_text(row.get("source_excerpt")),
                    questions=row.get("questions"),
                )
            )
        return cls(chunks=chunks)

    def ids(self) -> list[str]:
        return [chunk.chunk_id for chunk in self.chunks]

    def scores(self) -> list[float | None]:
        return [chunk.score for chunk in self.chunks]

    def to_state_patch(self) -> RuntimeStatePatch:
        return {
            "knowledge_chunks": [chunk.to_prompt_payload() for chunk in self.chunks]
        }


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _can_use_resolved_query(state: RuntimeStateInput) -> bool:
    return (
        str(state.get("turn_relation") or "").strip().lower() == "continuation"
        and normalize_cta(state.get("cta")) == CONTINUE_EXPLANATION_CTA
        and _optional_text(state.get("knowledge_query")) is not None
    )
