from dataclasses import dataclass, field
from typing import Mapping, cast
import hashlib

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
    query: str = ""

    @classmethod
    def from_state(cls, state: RuntimeStateInput) -> "KnowledgeSearchContext":
        return cls(
            project_id=state.get("project_id"),
            query=str(state.get("user_input") or ""),
        )

    @property
    def query_hash(self) -> str:
        return hash_query(self.query)


@dataclass(slots=True)
class KnowledgeChunk:
    chunk_id: str
    score: float | None
    content: str

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
                    content=str(row.get("content") or "")[:150],
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
