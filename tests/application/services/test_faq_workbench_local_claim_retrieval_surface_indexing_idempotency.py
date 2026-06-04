from __future__ import annotations

from dataclasses import dataclass

import pytest

from src.application.services.faq_workbench_local_claim_retrieval_surface_indexing_service import (
    CheckLocalClaimRetrievalSurfaceIndexedCommand,
    FaqWorkbenchLocalClaimRetrievalSurfaceIndexingService,
    LocalClaimRetrievalSurfaceEmbeddingResult,
    LocalClaimRetrievalSurfaceEntry,
)


@dataclass(slots=True)
class FakeGraphLoader:
    async def load_document_local_claim_graphs(self, command: object) -> object:
        raise AssertionError(f"unexpected graph load: {command}")


@dataclass(slots=True)
class FakeEmbeddingService:
    async def embed_passages(
        self,
        texts: list[str],
    ) -> LocalClaimRetrievalSurfaceEmbeddingResult:
        raise AssertionError(f"unexpected embedding call: {texts}")


@dataclass(slots=True)
class FakeRepository:
    indexed: bool

    async def has_indexed_local_claim_retrieval_entries_for_node_run(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
        node_run_id: str,
    ) -> bool:
        assert project_id == "project-1"
        assert document_id == "document-1"
        assert processing_run_id == "run-1"
        assert node_run_id == "node-run-1"
        return self.indexed

    async def replace_local_claim_retrieval_entries(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
        entries: tuple[LocalClaimRetrievalSurfaceEntry, ...],
    ) -> int:
        raise AssertionError(f"unexpected replace call: {entries}")


@pytest.mark.asyncio
async def test_local_claim_indexing_service_reports_existing_node_run_index() -> None:
    service = FaqWorkbenchLocalClaimRetrievalSurfaceIndexingService(
        graph_loader=FakeGraphLoader(),
        repository=FakeRepository(indexed=True),
        embedding_service=FakeEmbeddingService(),
    )

    result = await service.has_indexed_node_run(
        CheckLocalClaimRetrievalSurfaceIndexedCommand(
            project_id="project-1",
            document_id="document-1",
            processing_run_id="run-1",
            node_run_id="node-run-1",
        )
    )

    assert result.indexed is True


@pytest.mark.asyncio
async def test_local_claim_indexing_service_reports_missing_node_run_index() -> None:
    service = FaqWorkbenchLocalClaimRetrievalSurfaceIndexingService(
        graph_loader=FakeGraphLoader(),
        repository=FakeRepository(indexed=False),
        embedding_service=FakeEmbeddingService(),
    )

    result = await service.has_indexed_node_run(
        CheckLocalClaimRetrievalSurfaceIndexedCommand(
            project_id="project-1",
            document_id="document-1",
            processing_run_id="run-1",
            node_run_id="node-run-1",
        )
    )

    assert result.indexed is False
