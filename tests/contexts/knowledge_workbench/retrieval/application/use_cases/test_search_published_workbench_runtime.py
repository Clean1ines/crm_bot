from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from src.contexts.embedding_runtime.application.ports.embedding_generation_port import (
    EmbeddingGenerationRequest,
    EmbeddingGenerationResult,
)
from src.contexts.knowledge_workbench.retrieval.application.models.published_workbench_retrieval import (
    PublishedWorkbenchRetrievalResult,
    PublishedWorkbenchRetrievalSourceRef,
)
from src.contexts.knowledge_workbench.retrieval.application.use_cases.search_published_workbench_runtime import (
    PublishedWorkbenchRuntimeSearchEmbeddingError,
    SearchPublishedWorkbenchRuntime,
)


@dataclass(slots=True)
class FakeEmbeddingPort:
    requests: list[EmbeddingGenerationRequest] = field(default_factory=list)
    dimensions: int = 3
    vectors: tuple[tuple[float, ...], ...] = ((0.1, 0.2, 0.3),)

    async def embed(
        self,
        request: EmbeddingGenerationRequest,
    ) -> EmbeddingGenerationResult:
        self.requests.append(request)
        return EmbeddingGenerationResult(
            embeddings=self.vectors,
            model_id=request.model_id,
            dimensions=self.dimensions,
        )


@dataclass(slots=True)
class FakeRetrievalPort:
    calls: list[tuple[str, str, tuple[float, ...], str, int, int]] = field(
        default_factory=list
    )

    async def search(
        self,
        *,
        project_id: str,
        query_text: str,
        query_embedding,
        embedding_model_id: str,
        dimensions: int,
        limit: int,
    ) -> tuple[PublishedWorkbenchRetrievalResult, ...]:
        self.calls.append(
            (
                project_id,
                query_text,
                tuple(query_embedding),
                embedding_model_id,
                dimensions,
                limit,
            )
        )
        return (
            PublishedWorkbenchRetrievalResult(
                runtime_entry_id="runtime-entry-1",
                publication_id="publication-1",
                project_id=project_id,
                source_document_ref="source-document-1",
                fact_id="fact-1",
                curation_item_ref="item-1",
                claim="Published claim",
                possible_questions=("Question?",),
                exclusion_scope="",
                evidence_block=None,
                source_claim_refs=("raw-1",),
                embedding_text="Claim:\\nPublished claim",
                score=0.9,
                rank=1,
                source_ref=PublishedWorkbenchRetrievalSourceRef(
                    workflow_run_id="workflow-1",
                    source_document_ref="source-document-1",
                    curation_item_ref="item-1",
                    source_claim_refs=("raw-1",),
                ),
            ),
        )


@pytest.mark.asyncio
async def test_search_generates_query_embedding_and_calls_vector_adapter() -> None:
    embedding_port = FakeEmbeddingPort()
    retrieval_port = FakeRetrievalPort()

    result = await SearchPublishedWorkbenchRuntime(
        published_retrieval_port=retrieval_port,
        embedding_generation_port=embedding_port,
        embedding_model_id="model-384",
        embedding_dimensions=3,
    ).execute(project_id="project-1", query_text="  user question  ", limit=5)

    assert result[0].runtime_entry_id == "runtime-entry-1"
    assert embedding_port.requests == [
        EmbeddingGenerationRequest(
            texts=("user question",),
            model_id="model-384",
            expected_dimensions=3,
            task="retrieval.query",
        )
    ]
    assert retrieval_port.calls == [
        ("project-1", "user question", (0.1, 0.2, 0.3), "model-384", 3, 5)
    ]


@pytest.mark.asyncio
async def test_search_rejects_empty_query() -> None:
    with pytest.raises(ValueError):
        await SearchPublishedWorkbenchRuntime(
            published_retrieval_port=FakeRetrievalPort(),
            embedding_generation_port=FakeEmbeddingPort(),
            embedding_model_id="model-384",
            embedding_dimensions=3,
        ).execute(project_id="project-1", query_text="   ")


@pytest.mark.asyncio
async def test_search_rejects_embedding_count_mismatch() -> None:
    with pytest.raises(PublishedWorkbenchRuntimeSearchEmbeddingError):
        await SearchPublishedWorkbenchRuntime(
            published_retrieval_port=FakeRetrievalPort(),
            embedding_generation_port=FakeEmbeddingPort(vectors=()),
            embedding_model_id="model-384",
            embedding_dimensions=3,
        ).execute(project_id="project-1", query_text="question")


@pytest.mark.asyncio
async def test_search_rejects_embedding_dimension_mismatch() -> None:
    with pytest.raises(PublishedWorkbenchRuntimeSearchEmbeddingError):
        await SearchPublishedWorkbenchRuntime(
            published_retrieval_port=FakeRetrievalPort(),
            embedding_generation_port=FakeEmbeddingPort(
                dimensions=2,
                vectors=((0.1, 0.2),),
            ),
            embedding_model_id="model-384",
            embedding_dimensions=3,
        ).execute(project_id="project-1", query_text="question")
