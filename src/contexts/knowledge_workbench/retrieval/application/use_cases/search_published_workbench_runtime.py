from __future__ import annotations

from dataclasses import dataclass

from src.contexts.embedding_runtime.application.ports.embedding_generation_port import (
    EmbeddingGenerationPort,
    EmbeddingGenerationRequest,
)
from src.contexts.knowledge_workbench.retrieval.application.models.published_workbench_retrieval import (
    PublishedWorkbenchRetrievalResult,
)
from src.contexts.knowledge_workbench.retrieval.application.ports.published_workbench_retrieval_port import (
    PublishedWorkbenchRetrievalPort,
)


class PublishedWorkbenchRuntimeSearchEmbeddingError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class SearchPublishedWorkbenchRuntime:
    published_retrieval_port: PublishedWorkbenchRetrievalPort
    embedding_generation_port: EmbeddingGenerationPort
    embedding_model_id: str
    embedding_dimensions: int

    async def execute(
        self,
        *,
        project_id: str,
        query_text: str,
        limit: int = 10,
    ) -> tuple[PublishedWorkbenchRetrievalResult, ...]:
        project_id = _require_stripped(project_id, "project_id")
        query_text = _require_stripped(query_text, "query_text")
        if limit < 1:
            raise ValueError("limit must be positive")
        if not self.embedding_model_id.strip():
            raise ValueError("embedding_model_id must be non-empty")
        if self.embedding_dimensions < 1:
            raise ValueError("embedding_dimensions must be positive")

        embedding_result = await self.embedding_generation_port.embed(
            EmbeddingGenerationRequest(
                texts=(query_text,),
                model_id=self.embedding_model_id,
                expected_dimensions=self.embedding_dimensions,
                task="retrieval.query",
            )
        )

        if len(embedding_result.embeddings) != 1:
            raise PublishedWorkbenchRuntimeSearchEmbeddingError(
                "query embedding result must contain exactly one vector"
            )
        if embedding_result.dimensions != self.embedding_dimensions:
            raise PublishedWorkbenchRuntimeSearchEmbeddingError(
                "query embedding dimensions must match configured dimensions"
            )

        return await self.published_retrieval_port.search(
            project_id=project_id,
            query_text=query_text,
            query_embedding=embedding_result.embeddings[0],
            embedding_model_id=embedding_result.model_id,
            dimensions=embedding_result.dimensions,
            limit=limit,
        )


def _require_stripped(value: str, field_name: str) -> str:
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"{field_name} must be non-empty")
    return stripped
