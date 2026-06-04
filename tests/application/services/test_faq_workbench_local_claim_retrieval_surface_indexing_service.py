from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from src.application.services.faq_workbench_local_claim_retrieval_surface_indexing_service import (
    FaqWorkbenchLocalClaimRetrievalSurfaceIndexingService,
    IndexDocumentLocalClaimRetrievalSurfaceCommand,
    LocalClaimRetrievalSurfaceEmbeddingResult,
    LocalClaimRetrievalSurfaceEntry,
)
from src.domain.project_plane.knowledge_workbench.local_claim_search import (
    LocalClaimSearchDocument,
)


@dataclass(slots=True)
class FakeGraphLoader:
    async def load_document_local_claim_graphs(self, command: object) -> object:
        raise AssertionError(f"unexpected graph load: {command}")


@dataclass(slots=True)
class FakeEmbeddingService:
    texts: list[str] = field(default_factory=list)

    async def embed_passages(
        self,
        texts: list[str],
    ) -> LocalClaimRetrievalSurfaceEmbeddingResult:
        self.texts.extend(texts)
        return LocalClaimRetrievalSurfaceEmbeddingResult(
            embeddings=[
                [1.0, 0.0, 0.0],
                [0.98, 0.02, 0.0],
                [0.0, 1.0, 0.0],
            ][: len(texts)]
        )


@dataclass(slots=True)
class FakeRepository:
    entries: tuple[LocalClaimRetrievalSurfaceEntry, ...] = ()

    async def replace_local_claim_retrieval_entries(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
        entries: tuple[LocalClaimRetrievalSurfaceEntry, ...],
    ) -> int:
        self.entries = entries
        return len(entries)


def _doc(
    *,
    section_id: str,
    node_run_id: str,
    local_ref: str,
    claim: str,
) -> LocalClaimSearchDocument:
    return LocalClaimSearchDocument(
        search_document_id=f"{section_id}:{node_run_id}:{local_ref}",
        project_id="project-1",
        document_id="document-1",
        section_id=section_id,
        node_run_id=node_run_id,
        local_ref=local_ref,
        claim=claim,
        claim_kind="capability",
        granularity="atomic",
        triple_texts=(),
        possible_questions=(f"Question for {claim}",),
        scope="",
        exclusion_scope="",
        evidence_block=claim,
        relation_texts=(),
        search_text=f"claim: {claim}",
    )


@pytest.mark.asyncio
async def test_indexes_local_claim_search_documents_and_returns_vector_edges() -> None:
    repository = FakeRepository()
    embedding_service = FakeEmbeddingService()
    service = FaqWorkbenchLocalClaimRetrievalSurfaceIndexingService(
        graph_loader=FakeGraphLoader(),
        repository=repository,
        embedding_service=embedding_service,
    )

    result = await service.index_document_local_claim_retrieval_surface(
        IndexDocumentLocalClaimRetrievalSurfaceCommand(
            project_id="project-1",
            document_id="document-1",
            processing_run_id="run-1",
            search_documents=(
                _doc(
                    section_id="section-1",
                    node_run_id="node-1",
                    local_ref="c1",
                    claim="Бот отвечает клиентам в Telegram.",
                ),
                _doc(
                    section_id="section-2",
                    node_run_id="node-2",
                    local_ref="c2",
                    claim="AI-ассистент отвечает покупателям в Telegram.",
                ),
                _doc(
                    section_id="section-3",
                    node_run_id="node-3",
                    local_ref="c3",
                    claim="Менеджер видит историю переписки.",
                ),
            ),
            min_vector_similarity_score=0.95,
        )
    )

    assert result.indexed_entry_count == 3
    assert result.indexed_node_run_count == 3
    assert result.vector_edge_count == 1
    assert result.vector_similarity_edges[0].signals[0].signal_type == (
        "embedding_similarity"
    )
    assert len(repository.entries) == 3
    assert len(embedding_service.texts) == 3
    assert repository.entries[0].entry_id.startswith("local_claim:")


@pytest.mark.asyncio
async def test_empty_local_claim_documents_replace_existing_index_with_empty_set() -> (
    None
):
    repository = FakeRepository()
    service = FaqWorkbenchLocalClaimRetrievalSurfaceIndexingService(
        graph_loader=FakeGraphLoader(),
        repository=repository,
        embedding_service=FakeEmbeddingService(),
    )

    result = await service.index_document_local_claim_retrieval_surface(
        IndexDocumentLocalClaimRetrievalSurfaceCommand(
            project_id="project-1",
            document_id="document-1",
            processing_run_id="run-1",
            search_documents=(),
        )
    )

    assert result.indexed_entry_count == 0
    assert result.indexed_node_run_count == 0
    assert result.vector_similarity_edges == ()
