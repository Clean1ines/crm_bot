from __future__ import annotations

import re
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
class KnowledgeDocumentBlock:
    """Lossless source block extracted from an uploaded knowledge document."""

    content: str
    title: str = ""
    headings: tuple[str, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        content = _clean_block_content(self.content)
        if not content:
            raise ValueError("Knowledge document block content must not be empty")

        object.__setattr__(self, "content", content)
        object.__setattr__(self, "title", _clean_text(self.title))
        object.__setattr__(self, "headings", _clean_text_tuple(self.headings))
        object.__setattr__(self, "metadata", _immutable_metadata(self.metadata))


@dataclass(frozen=True, slots=True)
class ParsedKnowledgeDocument:
    source: KnowledgeDocumentSource
    title: str = ""
    chunks: tuple[KnowledgeChunkDraft, ...] = ()
    blocks: tuple[KnowledgeDocumentBlock, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "title", _clean_text(self.title))
        object.__setattr__(self, "chunks", _chunk_tuple(self.chunks))
        object.__setattr__(self, "blocks", _block_tuple(self.blocks))
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


def _clean_block_content(value: object) -> str:
    if not isinstance(value, str):
        return ""

    lines = [
        re.sub(r"[ \t]+", " ", line).rstrip()
        for line in value.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    ]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _clean_text_tuple(values: object) -> tuple[str, ...]:
    if values is None:
        return ()

    if isinstance(values, str):
        raw_values: tuple[object, ...] = (values,)
    elif isinstance(values, tuple):
        raw_values = values
    elif isinstance(values, list):
        raw_values = tuple(values)
    else:
        return ()

    result: list[str] = []
    for item in raw_values:
        text = _clean_text(item)
        if text and text not in result:
            result.append(text)

    return tuple(result)


def _chunk_tuple(value: object) -> tuple[KnowledgeChunkDraft, ...]:
    if not isinstance(value, tuple):
        raise TypeError("Parsed knowledge document chunks must be a tuple")

    for chunk in value:
        if not isinstance(chunk, KnowledgeChunkDraft):
            raise TypeError(
                "Parsed knowledge document chunks must contain KnowledgeChunkDraft"
            )

    return value


def _block_tuple(value: object) -> tuple[KnowledgeDocumentBlock, ...]:
    if not isinstance(value, tuple):
        raise TypeError("Parsed knowledge document blocks must be a tuple")

    for block in value:
        if not isinstance(block, KnowledgeDocumentBlock):
            raise TypeError(
                "Parsed knowledge document blocks must contain KnowledgeDocumentBlock"
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
