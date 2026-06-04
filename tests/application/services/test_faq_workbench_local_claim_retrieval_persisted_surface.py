from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from src.application.services.faq_workbench_local_claim_retrieval_service import (
    BuildDocumentLocalClaimRetrievalCommand,
    FaqWorkbenchLocalClaimRetrievalService,
    LoadIndexedLocalClaimRetrievalSurfaceCommand,
    LoadIndexedLocalClaimRetrievalSurfaceResult,
)
from src.application.services.faq_workbench_local_claim_retrieval_surface_indexing_service import (
    IndexDocumentLocalClaimRetrievalSurfaceCommand,
)
from src.domain.project_plane.knowledge_workbench import (
    LocalClaimSearchDocument,
    LocalClaimSimilarityEdge,
    LocalClaimSimilaritySignal,
)


@dataclass(slots=True)
class FailingGraphLoader:
    async def load_document_local_claim_graphs(self, command: object) -> object:
        raise AssertionError(f"graph loader must not be called: {command}")


@dataclass(slots=True)
class FailingIndexingService:
    calls: list[IndexDocumentLocalClaimRetrievalSurfaceCommand] = field(
        default_factory=list
    )

    async def index_document_local_claim_retrieval_surface(
        self,
        command: IndexDocumentLocalClaimRetrievalSurfaceCommand,
    ) -> object:
        self.calls.append(command)
        raise AssertionError(f"indexing service must not be called: {command}")


@dataclass(slots=True)
class FakeSurfaceReader:
    result: LoadIndexedLocalClaimRetrievalSurfaceResult
    calls: list[LoadIndexedLocalClaimRetrievalSurfaceCommand] = field(
        default_factory=list
    )

    async def load_indexed_local_claim_retrieval_surface(
        self,
        command: LoadIndexedLocalClaimRetrievalSurfaceCommand,
    ) -> LoadIndexedLocalClaimRetrievalSurfaceResult:
        self.calls.append(command)
        return self.result


def _doc(
    *,
    search_document_id: str,
    local_ref: str,
    claim: str,
) -> LocalClaimSearchDocument:
    return LocalClaimSearchDocument(
        search_document_id=search_document_id,
        project_id="project-1",
        document_id="document-1",
        section_id="section-1",
        node_run_id=f"node-{local_ref}",
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
async def test_local_claim_retrieval_uses_persisted_vector_surface_before_prompt_c() -> (
    None
):
    docs = (
        _doc(
            search_document_id="section-1:node-c1:c1",
            local_ref="c1",
            claim="Бот отвечает клиентам в Telegram.",
        ),
        _doc(
            search_document_id="section-2:node-c2:c2",
            local_ref="c2",
            claim="AI-ассистент отвечает покупателям в Telegram.",
        ),
    )
    vector_edge = LocalClaimSimilarityEdge(
        source_search_document_id=docs[0].search_document_id,
        target_search_document_id=docs[1].search_document_id,
        score=0.91,
        signals=(
            LocalClaimSimilaritySignal(
                signal_type="embedding_similarity",
                score=0.91,
            ),
        ),
    )
    reader = FakeSurfaceReader(
        result=LoadIndexedLocalClaimRetrievalSurfaceResult(
            search_documents=docs,
            vector_similarity_edges=(vector_edge,),
        )
    )
    indexing_service = FailingIndexingService()
    service = FaqWorkbenchLocalClaimRetrievalService(
        graph_loader=FailingGraphLoader(),
        retrieval_surface_indexing_service=indexing_service,
        retrieval_surface_reader=reader,
    )

    result = await service.build_document_local_claim_retrieval(
        BuildDocumentLocalClaimRetrievalCommand(
            project_id="project-1",
            document_id="document-1",
            processing_run_id="run-1",
        )
    )

    assert len(reader.calls) == 1
    assert reader.calls[0].processing_run_id == "run-1"
    assert indexing_service.calls == []

    assert result.claim_count == 2
    assert result.edge_count >= 1
    assert any(
        signal.signal_type == "embedding_similarity"
        for edge in result.similarity_edges
        for signal in edge.signals
    )
    assert result.group_count == 1
    assert result.unit_count == 1


@pytest.mark.asyncio
async def test_local_claim_retrieval_falls_back_when_persisted_surface_is_empty() -> (
    None
):
    class EmptyGraphLoader:
        async def load_document_local_claim_graphs(self, command: object) -> object:
            return type("GraphResult", (), {"graphs": ()})()

    reader = FakeSurfaceReader(
        result=LoadIndexedLocalClaimRetrievalSurfaceResult(
            search_documents=(),
            vector_similarity_edges=(),
        )
    )
    service = FaqWorkbenchLocalClaimRetrievalService(
        graph_loader=EmptyGraphLoader(),
        retrieval_surface_reader=reader,
    )

    result = await service.build_document_local_claim_retrieval(
        BuildDocumentLocalClaimRetrievalCommand(
            project_id="project-1",
            document_id="document-1",
            processing_run_id="run-1",
        )
    )

    assert len(reader.calls) == 1
    assert result.claim_count == 0
    assert result.edge_count == 0
