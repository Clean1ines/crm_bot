from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, cast


class ProjectAnswerPreviewValidationError(ValueError):
    pass


class RuntimeRagSearchPort(Protocol):
    async def search_with_expansion(
        self,
        project_id: str,
        query: str,
        thread_id: str | None = None,
        limit_per_query: int | None = None,
        final_limit: int | None = None,
    ) -> list[dict[str, object]]: ...


class ProjectRuntimeConfigurationLoaderPort(Protocol):
    async def load_project_configuration(self, project_id: str) -> object: ...


class AnswerPreviewPromptBuilderPort(Protocol):
    def __call__(
        self,
        *,
        user_input: str,
        knowledge_chunks: list[object],
        project_configuration: Mapping[str, object] | None,
        target_language: str,
    ) -> str: ...


class AnswerCompletionPort(Protocol):
    async def complete(
        self,
        prompt: str,
        *,
        project_configuration: Mapping[str, object] | None = None,
    ) -> str: ...


@dataclass(frozen=True, slots=True)
class ProjectAnswerPreviewFact:
    id: str
    content: str
    score: float
    method: str
    source: str | None = None
    title: str | None = None
    entry_kind: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "content": self.content,
            "score": self.score,
            "method": self.method,
            "source": self.source,
            "title": self.title,
            "entry_kind": self.entry_kind,
        }


@dataclass(frozen=True, slots=True)
class ProjectAnswerPreviewResult:
    query: str
    answer: str
    facts: tuple[ProjectAnswerPreviewFact, ...]
    is_empty: bool
    method: str = "client_answer_preview"
    retrieval_mode: str = "runtime_equivalent"

    def to_dict(self) -> dict[str, object]:
        facts = [fact.to_dict() for fact in self.facts]
        return {
            "query": self.query,
            "answer": self.answer,
            "is_empty": self.is_empty,
            "method": self.method,
            "retrieval_mode": self.retrieval_mode,
            "debug_context": {"facts": facts},
            "facts": facts,
        }


class ProjectAnswerPreviewService:
    def __init__(
        self,
        *,
        rag_service: RuntimeRagSearchPort,
        runtime_loader: ProjectRuntimeConfigurationLoaderPort,
        prompt_builder: AnswerPreviewPromptBuilderPort,
        answer_completion: AnswerCompletionPort,
    ) -> None:
        self._rag_service = rag_service
        self._runtime_loader = runtime_loader
        self._prompt_builder = prompt_builder
        self._answer_completion = answer_completion

    async def execute(
        self,
        *,
        project_id: str,
        question: str,
        limit: int = 5,
    ) -> ProjectAnswerPreviewResult:
        normalized_question = " ".join(str(question or "").split())
        if not normalized_question:
            raise ProjectAnswerPreviewValidationError(
                "question must be non-empty string"
            )

        normalized_limit = max(1, min(int(limit), 10))
        runtime_context = await self._runtime_loader.load_project_configuration(
            project_id
        )
        project_configuration = _runtime_context_to_mapping(runtime_context)

        chunks = await self._rag_service.search_with_expansion(
            project_id=project_id,
            query=normalized_question,
            thread_id=None,
            final_limit=normalized_limit,
        )
        facts = tuple(_fact_from_chunk(chunk) for chunk in chunks)

        prompt = self._prompt_builder(
            user_input=normalized_question,
            knowledge_chunks=cast(list[object], chunks),
            project_configuration=project_configuration,
            target_language="unknown",
        )
        generated_answer = (
            await self._answer_completion.complete(
                prompt,
                project_configuration=project_configuration,
            )
        ).strip()

        if not generated_answer:
            generated_answer = (
                "В опубликованной базе знаний пока нет достаточного контекста, "
                "чтобы ответить на этот вопрос."
                if not facts
                else "Не получилось сгенерировать ответ по найденному контексту."
            )

        return ProjectAnswerPreviewResult(
            query=normalized_question,
            answer=generated_answer,
            facts=facts,
            is_empty=not facts,
        )


def _runtime_context_to_mapping(value: object) -> Mapping[str, object]:
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        payload = to_dict()
    else:
        payload = value
    if isinstance(payload, Mapping):
        return {str(key): item for key, item in payload.items()}
    return {}


def _fact_from_chunk(chunk: Mapping[str, object]) -> ProjectAnswerPreviewFact:
    return ProjectAnswerPreviewFact(
        id=_text(chunk.get("id")),
        content=_text(chunk.get("content")),
        score=_float(chunk.get("score")),
        method=_text(chunk.get("method"), default="runtime_search"),
        source=_optional_text(chunk.get("source")),
        title=_optional_text(chunk.get("title")),
        entry_kind=_optional_text(chunk.get("entry_kind")),
    )


def _text(value: object, *, default: str = "") -> str:
    if value is None:
        return default
    text = str(value)
    return text if text else default


def _optional_text(value: object) -> str | None:
    text = _text(value).strip()
    return text or None


def _float(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
