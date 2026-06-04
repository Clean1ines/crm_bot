from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import pytest

from src.application.workbench_commands.delete_document import (
    WorkbenchDocumentDeleteCommand,
    WorkbenchDocumentDeleteService,
)
from src.domain.project_plane.knowledge_workbench.documents import (
    KnowledgeDocumentStatus,
)
from src.domain.project_plane.knowledge_workbench.processing import (
    ProcessingRunStatus,
)


@dataclass(frozen=True, slots=True)
class FakeDocument:
    project_id: str = "project-1"
    document_id: str = "document-1"
    status: KnowledgeDocumentStatus = KnowledgeDocumentStatus.PUBLISHED
    current_processing_run_id: str | None = None


@dataclass(slots=True)
class FakeRepository:
    cleanups: list[tuple[str, str]] = field(default_factory=list)
    persisted: bool = False

    async def get_document(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> FakeDocument | None:
        assert project_id == "project-1"
        assert document_id == "document-1"
        return FakeDocument()

    async def get_processing_run(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
    ) -> object | None:
        raise AssertionError("published document should not load processing run")

    async def persist_document_delete_transition(
        self,
        *,
        project_id: str,
        document_id: str,
        current_processing_run_id: str | None,
        document_status: KnowledgeDocumentStatus,
        processing_run_status: ProcessingRunStatus | None,
        deleted_at: datetime,
    ) -> None:
        assert project_id == "project-1"
        assert document_id == "document-1"
        assert current_processing_run_id is None
        assert document_status is KnowledgeDocumentStatus.DELETED
        assert processing_run_status is None
        assert deleted_at.tzinfo is not None
        self.persisted = True

    async def cleanup_document_final_retrieval_projections(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> int:
        self.cleanups.append((project_id, document_id))
        return 4


@pytest.mark.asyncio
async def test_delete_document_cleans_final_retrieval_projections() -> None:
    repository = FakeRepository()
    service = WorkbenchDocumentDeleteService(repository)

    result = await service.delete_document(
        WorkbenchDocumentDeleteCommand(
            project_id="project-1",
            document_id="document-1",
        )
    )

    assert repository.persisted is True
    assert repository.cleanups == [("project-1", "document-1")]
    assert result.runtime_publication_removed is True
    assert result.document_status is KnowledgeDocumentStatus.DELETED
