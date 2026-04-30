from dataclasses import asdict, dataclass

from src.domain.project_plane.knowledge_views import KnowledgeSearchResultView


@dataclass(slots=True)
class KnowledgeUploadResultDto:
    message: str
    chunks: int

    @classmethod
    def create(cls, *, message: str, chunks: int) -> "KnowledgeUploadResultDto":
        return cls(message=message, chunks=chunks)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class KnowledgePreviewRequestDto:
    question: str
    limit: int = 5

    def normalized_question(self) -> str:
        return self.question.strip()

    def normalized_limit(self) -> int:
        return max(1, min(int(self.limit), 10))


@dataclass(frozen=True, slots=True)
class KnowledgePreviewResultDto:
    id: str
    content: str
    score: float
    method: str
    source: str | None
    document_id: str | None
    document_status: str | None

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
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "content": self.content,
            "answer": self.content,
            "score": self.score,
            "method": self.method,
            "source": self.source,
            "document_id": self.document_id,
            "document_status": self.document_status,
        }


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
