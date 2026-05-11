from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping

from src.domain.project_plane.knowledge_chunks import KnowledgeChunkDraft


@dataclass(frozen=True, slots=True)
class KnowledgeDocumentSource:
    filename: str
    content_type: str = ""
    parser_name: str = ""

    def __post_init__(self) -> None:
        filename = _clean_text(self.filename)
        if not filename:
            raise ValueError("Knowledge document source filename must not be empty")

        object.__setattr__(self, "filename", filename)
        object.__setattr__(self, "content_type", _clean_text(self.content_type))
        object.__setattr__(self, "parser_name", _clean_text(self.parser_name))


@dataclass(frozen=True, slots=True)
class ParsedKnowledgeDocument:
    source: KnowledgeDocumentSource
    title: str = ""
    chunks: tuple[KnowledgeChunkDraft, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "title", _clean_text(self.title))
        object.__setattr__(self, "chunks", _chunk_tuple(self.chunks))
        object.__setattr__(self, "metadata", _immutable_metadata(self.metadata))

    @property
    def has_chunks(self) -> bool:
        return bool(self.chunks)

    @property
    def answerable_chunks(self) -> tuple[KnowledgeChunkDraft, ...]:
        return tuple(chunk for chunk in self.chunks if chunk.is_answerable)


def _clean_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.strip().split())


def _chunk_tuple(value: object) -> tuple[KnowledgeChunkDraft, ...]:
    if not isinstance(value, tuple):
        raise TypeError("Parsed knowledge document chunks must be a tuple")

    for chunk in value:
        if not isinstance(chunk, KnowledgeChunkDraft):
            raise TypeError(
                "Parsed knowledge document chunks must contain KnowledgeChunkDraft"
            )

    return value


def _immutable_metadata(value: Mapping[str, object] | object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        return MappingProxyType({})

    safe: dict[str, object] = {}
    for raw_key, raw_value in value.items():
        key = _clean_text(raw_key)
        if key:
            safe[key] = raw_value

    return MappingProxyType(safe)
