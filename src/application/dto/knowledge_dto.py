from collections.abc import Mapping
from dataclasses import asdict, dataclass

from src.domain.project_plane.json_types import JsonObject, json_value_from_unknown
from src.domain.project_plane.knowledge_views import (
    KnowledgeSearchResultView,
    KnowledgeSearchTraceView,
    SourceRefView,
)
from src.domain.project_plane.knowledge_preprocessing import (
    KnowledgePreprocessingMode,
    normalize_preprocessing_mode,
)


@dataclass(slots=True)
class KnowledgeUploadResultDto:
    message: str
    chunks: int
    document_id: str | None = None
    preprocessing_mode: str | None = None
    preprocessing_status: str | None = None
    structured_entries: int | None = None

    @classmethod
    def create(
        cls,
        *,
        message: str,
        chunks: int,
        document_id: str | None = None,
        preprocessing_mode: str | None = None,
        preprocessing_status: str | None = None,
        structured_entries: int | None = None,
    ) -> "KnowledgeUploadResultDto":
        return cls(
            message=message,
            chunks=chunks,
            document_id=document_id,
            preprocessing_mode=preprocessing_mode,
            preprocessing_status=preprocessing_status,
            structured_entries=structured_entries,
        )

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        return {key: value for key, value in payload.items() if value is not None}


@dataclass(frozen=True, slots=True)
class KnowledgeUploadJobPayloadDto:
    project_id: str
    document_id: str
    file_name: str
    preprocessing_mode: str
    chunks: list[JsonObject]

    def to_dict(self) -> JsonObject:
        return {
            "project_id": self.project_id,
            "document_id": self.document_id,
            "file_name": self.file_name,
            "preprocessing_mode": self.preprocessing_mode,
            "chunks": json_value_from_unknown(self.chunks),
        }

    def normalized_preprocessing_mode(self) -> KnowledgePreprocessingMode:
        return normalize_preprocessing_mode(self.preprocessing_mode)

    @classmethod
    def from_mapping(
        cls, payload: Mapping[str, object]
    ) -> "KnowledgeUploadJobPayloadDto":
        project_id = str(payload.get("project_id") or "").strip()
        document_id = str(payload.get("document_id") or "").strip()
        file_name = str(payload.get("file_name") or "").strip()
        preprocessing_mode = str(payload.get("preprocessing_mode") or "").strip()
        raw_chunks = payload.get("chunks")

        if not project_id:
            raise ValueError("knowledge upload payload missing project_id")
        if not document_id:
            raise ValueError("knowledge upload payload missing document_id")
        if not file_name:
            raise ValueError("knowledge upload payload missing file_name")
        if not preprocessing_mode:
            raise ValueError("knowledge upload payload missing preprocessing_mode")
        if not isinstance(raw_chunks, list):
            raise ValueError("knowledge upload payload chunks must be a list")

        chunks: list[JsonObject] = []
        for item in raw_chunks:
            if not isinstance(item, Mapping):
                raise ValueError("knowledge upload payload chunk must be an object")
            chunk = {
                str(key): json_value_from_unknown(value) for key, value in item.items()
            }
            content = str(chunk.get("content") or "").strip()
            if not content:
                raise ValueError("knowledge upload payload chunk missing content")
            chunk["content"] = content
            chunks.append(chunk)

        return cls(
            project_id=project_id,
            document_id=document_id,
            file_name=file_name,
            preprocessing_mode=preprocessing_mode,
            chunks=chunks,
        )


@dataclass(frozen=True, slots=True)
class KnowledgeUploadRequestDto:
    preprocessing_mode: str = "plain"

    def normalized_preprocessing_mode(self) -> KnowledgePreprocessingMode:
        return normalize_preprocessing_mode(self.preprocessing_mode)


@dataclass(frozen=True, slots=True)
class KnowledgePreviewRequestDto:
    question: str
    limit: int = 5

    def normalized_question(self) -> str:
        return self.question.strip()

    def normalized_limit(self) -> int:
        return max(1, min(int(self.limit), 10))


@dataclass(frozen=True, slots=True)
class KnowledgeSearchTraceDto:
    matched_fields: tuple[str, ...]
    lexical_score: float
    vector_score: float
    exact_question_match: bool
    title_match: bool
    length_penalty: float
    final_score: float
    retrieval_surface_role: str
    displayed_field: str
    is_production_safe: bool

    @classmethod
    def from_view(cls, trace: KnowledgeSearchTraceView) -> "KnowledgeSearchTraceDto":
        return cls(
            matched_fields=trace.matched_fields,
            lexical_score=trace.lexical_score,
            vector_score=trace.vector_score,
            exact_question_match=trace.exact_question_match,
            title_match=trace.title_match,
            length_penalty=trace.length_penalty,
            final_score=trace.final_score,
            retrieval_surface_role=trace.retrieval_surface_role,
            displayed_field=trace.displayed_field,
            is_production_safe=trace.is_production_safe,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "matched_fields": list(self.matched_fields),
            "lexical_score": self.lexical_score,
            "vector_score": self.vector_score,
            "exact_question_match": self.exact_question_match,
            "title_match": self.title_match,
            "length_penalty": self.length_penalty,
            "final_score": self.final_score,
            "retrieval_surface_role": self.retrieval_surface_role,
            "displayed_field": self.displayed_field,
            "is_production_safe": self.is_production_safe,
        }


@dataclass(frozen=True, slots=True)
class SourceRefDto:
    quote: str
    source_index: int | None = None
    source_chunk_id: str | None = None
    start_offset: int | None = None
    end_offset: int | None = None
    confidence: float | None = None

    @classmethod
    def from_view(cls, source_ref: SourceRefView) -> "SourceRefDto":
        return cls(
            quote=source_ref.quote,
            source_index=source_ref.source_index,
            source_chunk_id=source_ref.source_chunk_id,
            start_offset=source_ref.start_offset,
            end_offset=source_ref.end_offset,
            confidence=source_ref.confidence,
        )

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {"quote": self.quote}
        if self.source_index is not None:
            payload["source_index"] = self.source_index
        if self.source_chunk_id is not None:
            payload["source_chunk_id"] = self.source_chunk_id
        if self.start_offset is not None:
            payload["start_offset"] = self.start_offset
        if self.end_offset is not None:
            payload["end_offset"] = self.end_offset
        if self.confidence is not None:
            payload["confidence"] = self.confidence
        return payload


@dataclass(frozen=True, slots=True)
class KnowledgePreviewResultDto:
    id: str
    content: str
    score: float
    method: str
    source: str | None
    document_id: str | None
    document_status: str | None
    entry_kind: str | None = None
    title: str | None = None
    source_excerpt: str | None = None
    source_refs: tuple[SourceRefDto, ...] = ()
    questions: object | None = None
    synonyms: object | None = None
    tags: object | None = None
    trace: KnowledgeSearchTraceDto | None = None

    @classmethod
    def from_search_result(
        cls,
        result: KnowledgeSearchResultView,
    ) -> "KnowledgePreviewResultDto":
        return cls(
            id=result.id,
            content=result.content,
            score=result.score,
            method=result.method,
            source=result.source,
            document_id=result.document_id,
            document_status=result.document_status,
            entry_kind=result.entry_kind,
            title=result.title,
            source_excerpt=result.source_excerpt,
            source_refs=tuple(
                SourceRefDto.from_view(ref) for ref in result.source_refs
            ),
            questions=result.questions,
            synonyms=result.synonyms,
            tags=result.tags,
            trace=(
                KnowledgeSearchTraceDto.from_view(result.trace)
                if result.trace is not None
                else None
            ),
        )

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "id": self.id,
            "content": self.content,
            "answer": self.content,
            "score": self.score,
            "method": self.method,
            "source": self.source,
            "document_id": self.document_id,
            "document_status": self.document_status,
        }

        if self.source_refs:
            payload["source_refs"] = [
                source_ref.to_dict() for source_ref in self.source_refs
            ]

        optional_fields = {
            "entry_kind": self.entry_kind,
            "title": self.title,
            "source_excerpt": self.source_excerpt,
            "questions": self.questions,
            "synonyms": self.synonyms,
            "tags": self.tags,
            "trace": self.trace.to_dict() if self.trace is not None else None,
        }
        for key, value in optional_fields.items():
            if value is not None:
                payload[key] = value

        return payload


@dataclass(frozen=True, slots=True)
class KnowledgePreviewResponseDto:
    query: str
    best_result: KnowledgePreviewResultDto | None
    top_results: list[KnowledgePreviewResultDto]
    is_empty: bool

    @classmethod
    def empty(cls, *, query: str) -> "KnowledgePreviewResponseDto":
        return cls(query=query, best_result=None, top_results=[], is_empty=True)

    @classmethod
    def from_results(
        cls,
        *,
        query: str,
        results: list[KnowledgeSearchResultView],
    ) -> "KnowledgePreviewResponseDto":
        preview_results = [
            KnowledgePreviewResultDto.from_search_result(result) for result in results
        ]
        return cls(
            query=query,
            best_result=preview_results[0] if preview_results else None,
            top_results=preview_results,
            is_empty=not preview_results,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "query": self.query,
            "best_result": self.best_result.to_dict() if self.best_result else None,
            "top_results": [result.to_dict() for result in self.top_results],
            "is_empty": self.is_empty,
        }
