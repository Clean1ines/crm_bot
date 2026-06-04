from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass

from src.domain.project_plane.knowledge_views import (
    KnowledgeSearchResultView,
    KnowledgeSearchTraceView,
)
from src.domain.project_plane.production_retrieval import ProductionRetrievalMode

KNOWLEDGE_PREVIEW_RETRIEVAL_MODE_RUNTIME_EQUIVALENT = "runtime_equivalent"
KNOWLEDGE_PREVIEW_RETRIEVAL_MODE_LEXICAL_DEBUG = (
    ProductionRetrievalMode.LEXICAL_DEBUG.value
)


@dataclass(frozen=True, slots=True)
class KnowledgePreviewRequestDto:
    question: str
    limit: int = 5
    retrieval_mode: str = KNOWLEDGE_PREVIEW_RETRIEVAL_MODE_RUNTIME_EQUIVALENT

    def normalized_question(self) -> str:
        return self.question.strip()

    def normalized_limit(self) -> int:
        return max(1, min(int(self.limit), 10))

    def normalized_retrieval_mode_value(self) -> str:
        value = str(
            self.retrieval_mode or KNOWLEDGE_PREVIEW_RETRIEVAL_MODE_RUNTIME_EQUIVALENT
        ).strip()
        if value == KNOWLEDGE_PREVIEW_RETRIEVAL_MODE_LEXICAL_DEBUG:
            return KNOWLEDGE_PREVIEW_RETRIEVAL_MODE_LEXICAL_DEBUG
        return KNOWLEDGE_PREVIEW_RETRIEVAL_MODE_RUNTIME_EQUIVALENT

    def normalized_production_retrieval_mode(self) -> ProductionRetrievalMode:
        value = self.normalized_retrieval_mode_value()
        if value == KNOWLEDGE_PREVIEW_RETRIEVAL_MODE_LEXICAL_DEBUG:
            return ProductionRetrievalMode.LEXICAL_DEBUG
        return ProductionRetrievalMode.RUNTIME_EQUIVALENT_PREVIEW


@dataclass(frozen=True, slots=True)
class KnowledgePreviewResultDto:
    id: str
    title: str
    content: str
    score: float
    method: str
    source: str | None = None
    document_id: str | None = None
    document_status: str | None = None
    entry_kind: str | None = None
    source_excerpt: str | None = None
    questions: tuple[str, ...] = ()
    synonyms: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    trace: KnowledgeSearchTraceView | None = None

    @classmethod
    def from_search_result(
        cls,
        result: KnowledgeSearchResultView,
    ) -> "KnowledgePreviewResultDto":
        return cls(
            id=result.id,
            title=result.title or "",
            content=result.content,
            score=float(result.score),
            method=result.method,
            source=result.source,
            document_id=result.document_id,
            document_status=result.document_status,
            entry_kind=result.entry_kind,
            source_excerpt=result.source_excerpt,
            questions=_string_tuple(result.questions),
            synonyms=_string_tuple(result.synonyms),
            tags=_string_tuple(result.tags),
            trace=result.trace,
        )

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "answer": self.content,
            "score": self.score,
            "method": self.method,
            "questions": list(self.questions),
            "synonyms": list(self.synonyms),
            "tags": list(self.tags),
        }
        if self.source is not None:
            payload["source"] = self.source
        if self.document_id is not None:
            payload["document_id"] = self.document_id
        if self.document_status is not None:
            payload["document_status"] = self.document_status
        if self.entry_kind is not None:
            payload["entry_kind"] = self.entry_kind
        if self.source_excerpt is not None:
            payload["source_excerpt"] = self.source_excerpt
        if self.trace is not None:
            payload["trace"] = _trace_to_dict(self.trace)
        return payload


@dataclass(slots=True)
class KnowledgePreviewResponseDto:
    query: str
    best_result: KnowledgePreviewResultDto | None
    top_results: list[KnowledgePreviewResultDto]
    is_empty: bool
    retrieval_mode: str = KNOWLEDGE_PREVIEW_RETRIEVAL_MODE_RUNTIME_EQUIVALENT
    method: str = "production_runtime_search"
    trace: Mapping[str, object] | None = None

    @classmethod
    def empty(
        cls,
        *,
        query: str,
        retrieval_mode: str = KNOWLEDGE_PREVIEW_RETRIEVAL_MODE_RUNTIME_EQUIVALENT,
        method: str = "production_runtime_search",
        trace: Mapping[str, object] | None = None,
    ) -> "KnowledgePreviewResponseDto":
        return cls(
            query=query,
            best_result=None,
            top_results=[],
            is_empty=True,
            retrieval_mode=retrieval_mode,
            method=method,
            trace=trace,
        )

    @classmethod
    def from_results(
        cls,
        *,
        query: str,
        results: list[KnowledgeSearchResultView],
        retrieval_mode: str = KNOWLEDGE_PREVIEW_RETRIEVAL_MODE_RUNTIME_EQUIVALENT,
        method: str = "production_runtime_search",
        trace: Mapping[str, object] | None = None,
    ) -> "KnowledgePreviewResponseDto":
        preview_results = [
            KnowledgePreviewResultDto.from_search_result(result) for result in results
        ]
        return cls(
            query=query,
            best_result=preview_results[0] if preview_results else None,
            top_results=preview_results,
            is_empty=not preview_results,
            retrieval_mode=retrieval_mode,
            method=method,
            trace=trace,
        )

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "query": self.query,
            "is_empty": self.is_empty,
            "retrieval_mode": self.retrieval_mode,
            "method": self.method,
            "best_result": self.best_result.to_dict()
            if self.best_result is not None
            else None,
            "top_results": [result.to_dict() for result in self.top_results],
        }
        if self.trace is not None:
            payload["trace"] = dict(self.trace)
        return payload


def _metadata_text_list(metadata: Mapping[str, object], key: str) -> list[str]:
    value = metadata.get(key)
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, list | tuple):
        return [str(item) for item in value if str(item).strip()]
    return []


def _metadata_int(metadata: Mapping[str, object], key: str) -> int | None:
    value = metadata.get(key)
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _metadata_int_list(metadata: Mapping[str, object], key: str) -> tuple[int, ...]:
    value = metadata.get(key)
    if isinstance(value, list | tuple):
        result: list[int] = []
        for item in value:
            if isinstance(item, bool) or item is None:
                continue
            if isinstance(item, int):
                result.append(item)
            elif isinstance(item, float) and item.is_integer():
                result.append(int(item))
            elif isinstance(item, str) and item.strip().isdigit():
                result.append(int(item.strip()))
        return tuple(result)
    single = _metadata_int(metadata, key)
    return (single,) if single is not None else ()


def _string_tuple(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        cleaned = value.strip()
        return (cleaned,) if cleaned else ()
    if isinstance(value, list | tuple | set):
        return tuple(str(item).strip() for item in value if str(item).strip())
    cleaned = str(value).strip()
    return (cleaned,) if cleaned else ()


def _trace_to_dict(trace: KnowledgeSearchTraceView) -> dict[str, object]:
    return asdict(trace)
