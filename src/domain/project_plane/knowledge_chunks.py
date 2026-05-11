from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping


class KnowledgeChunkRole(StrEnum):
    ANSWER_KNOWLEDGE = "answer_knowledge"
    FAQ = "faq"
    INSTRUCTION = "instruction"
    PRICE_LIST = "price_list"
    RETRIEVAL_GUIDELINE = "retrieval_guideline"
    INTERNAL_EVAL_TEST = "internal_eval_test"
    NEGATIVE_TEST = "negative_test"

    @property
    def is_answerable(self) -> bool:
        return self in {
            KnowledgeChunkRole.ANSWER_KNOWLEDGE,
            KnowledgeChunkRole.FAQ,
            KnowledgeChunkRole.PRICE_LIST,
            KnowledgeChunkRole.INSTRUCTION,
        }


ANSWERABLE_KNOWLEDGE_ROLES = frozenset(
    {
        KnowledgeChunkRole.ANSWER_KNOWLEDGE,
        KnowledgeChunkRole.FAQ,
        KnowledgeChunkRole.INSTRUCTION,
        KnowledgeChunkRole.PRICE_LIST,
    }
)

NON_ANSWER_KNOWLEDGE_ROLES = frozenset(
    {
        KnowledgeChunkRole.RETRIEVAL_GUIDELINE,
        KnowledgeChunkRole.INTERNAL_EVAL_TEST,
        KnowledgeChunkRole.NEGATIVE_TEST,
    }
)


@dataclass(frozen=True, slots=True)
class KnowledgeSectionPath:
    document_title: str = ""
    headings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "document_title", _clean_text(self.document_title))
        object.__setattr__(self, "headings", _clean_text_tuple(self.headings))

    @property
    def title(self) -> str:
        parts = [self.document_title, *self.headings]
        return " / ".join(part for part in parts if part)

    @property
    def leaf(self) -> str:
        if self.headings:
            return self.headings[-1]
        return self.document_title


@dataclass(frozen=True, slots=True)
class KnowledgeChunkDraft:
    content: str
    role: KnowledgeChunkRole = KnowledgeChunkRole.ANSWER_KNOWLEDGE
    title: str = ""
    source_excerpt: str = ""
    section_path: KnowledgeSectionPath = field(default_factory=KnowledgeSectionPath)
    questions: tuple[str, ...] = ()
    synonyms: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    embedding_text: str = ""
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        content = _clean_text(self.content)
        if not content:
            raise ValueError("Knowledge chunk content must not be empty")

        role = self.role
        if not isinstance(role, KnowledgeChunkRole):
            raise TypeError("Knowledge chunk role must be a KnowledgeChunkRole")

        object.__setattr__(self, "content", content)
        object.__setattr__(self, "title", _clean_text(self.title))
        object.__setattr__(self, "source_excerpt", _clean_text(self.source_excerpt))
        object.__setattr__(self, "questions", _clean_text_tuple(self.questions))
        object.__setattr__(self, "synonyms", _clean_text_tuple(self.synonyms))
        object.__setattr__(self, "tags", _clean_text_tuple(self.tags))
        object.__setattr__(self, "embedding_text", _clean_text(self.embedding_text))
        object.__setattr__(self, "metadata", _immutable_metadata(self.metadata))

    @property
    def is_answerable(self) -> bool:
        return self.role in ANSWERABLE_KNOWLEDGE_ROLES

    @property
    def effective_title(self) -> str:
        return self.title or self.section_path.title

    @property
    def effective_excerpt(self) -> str:
        return self.source_excerpt or _excerpt_from_content(self.content)

    def with_role(self, role: KnowledgeChunkRole) -> KnowledgeChunkDraft:
        return KnowledgeChunkDraft(
            content=self.content,
            role=role,
            title=self.title,
            source_excerpt=self.source_excerpt,
            section_path=self.section_path,
            questions=self.questions,
            synonyms=self.synonyms,
            tags=self.tags,
            embedding_text=self.embedding_text,
            metadata=self.metadata,
        )

    def with_embedding_text(self, embedding_text: str) -> KnowledgeChunkDraft:
        return KnowledgeChunkDraft(
            content=self.content,
            role=self.role,
            title=self.title,
            source_excerpt=self.source_excerpt,
            section_path=self.section_path,
            questions=self.questions,
            synonyms=self.synonyms,
            tags=self.tags,
            embedding_text=embedding_text,
            metadata=self.metadata,
        )


@dataclass(frozen=True, slots=True)
class KnowledgeChunk:
    project_id: str
    document_id: str
    content: str
    role: KnowledgeChunkRole
    title: str
    source_excerpt: str
    section_path: KnowledgeSectionPath
    questions: tuple[str, ...]
    synonyms: tuple[str, ...]
    tags: tuple[str, ...]
    embedding_text: str
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not _clean_text(self.project_id):
            raise ValueError("Knowledge chunk project_id must not be empty")
        if not _clean_text(self.document_id):
            raise ValueError("Knowledge chunk document_id must not be empty")
        if not _clean_text(self.content):
            raise ValueError("Knowledge chunk content must not be empty")
        if not isinstance(self.role, KnowledgeChunkRole):
            raise TypeError("Knowledge chunk role must be a KnowledgeChunkRole")

        object.__setattr__(self, "project_id", _clean_text(self.project_id))
        object.__setattr__(self, "document_id", _clean_text(self.document_id))
        object.__setattr__(self, "content", _clean_text(self.content))
        object.__setattr__(self, "title", _clean_text(self.title))
        object.__setattr__(self, "source_excerpt", _clean_text(self.source_excerpt))
        object.__setattr__(self, "questions", _clean_text_tuple(self.questions))
        object.__setattr__(self, "synonyms", _clean_text_tuple(self.synonyms))
        object.__setattr__(self, "tags", _clean_text_tuple(self.tags))
        object.__setattr__(self, "embedding_text", _clean_text(self.embedding_text))
        object.__setattr__(self, "metadata", _immutable_metadata(self.metadata))

    @property
    def is_answerable(self) -> bool:
        return self.role in ANSWERABLE_KNOWLEDGE_ROLES

    @classmethod
    def from_draft(
        cls,
        *,
        project_id: str,
        document_id: str,
        draft: KnowledgeChunkDraft,
    ) -> KnowledgeChunk:
        return cls(
            project_id=project_id,
            document_id=document_id,
            content=draft.content,
            role=draft.role,
            title=draft.effective_title,
            source_excerpt=draft.effective_excerpt,
            section_path=draft.section_path,
            questions=draft.questions,
            synonyms=draft.synonyms,
            tags=draft.tags,
            embedding_text=draft.embedding_text,
            metadata=draft.metadata,
        )


def _clean_text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.strip().split())


def _clean_text_tuple(values: object) -> tuple[str, ...]:
    if isinstance(values, str):
        candidates: tuple[object, ...] = (values,)
    elif isinstance(values, tuple):
        candidates = values
    elif isinstance(values, list):
        candidates = tuple(values)
    else:
        return ()

    result: list[str] = []
    for item in candidates:
        cleaned = _clean_text(item)
        if cleaned and cleaned not in result:
            result.append(cleaned)
    return tuple(result)


def _immutable_metadata(value: Mapping[str, object] | object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        return MappingProxyType({})

    safe: dict[str, object] = {}
    for raw_key, raw_value in value.items():
        key = _clean_text(raw_key)
        if key:
            safe[key] = raw_value
    return MappingProxyType(safe)


def _excerpt_from_content(content: str, *, max_chars: int = 420) -> str:
    normalized = _clean_text(content)
    if len(normalized) <= max_chars:
        return normalized
    return normalized[:max_chars].rstrip() + "..."
