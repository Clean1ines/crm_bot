from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

import pytest

from src.application.workbench_commands.clear_project import (
    WorkbenchProjectClearCommand,
    WorkbenchProjectClearService,
)
from src.domain.project_plane.knowledge_workbench.documents import (
    KnowledgeDocumentStatus,
)
from src.domain.project_plane.knowledge_workbench.processing import (
    ProcessingRunStatus,
)


@dataclass(slots=True)
class FakeRepository:
    cleanups: list[str] = field(default_factory=list)
    persisted: bool = False

    async def persist_project_clear_transition(
        self,
        *,
        project_id: str,
        document_status: KnowledgeDocumentStatus,
        processing_run_status: ProcessingRunStatus,
        cleared_at: datetime,
    ) -> int:
        assert project_id == "project-1"
        assert document_status is KnowledgeDocumentStatus.DELETED
        assert processing_run_status is ProcessingRunStatus.DELETED
        assert cleared_at.tzinfo is not None
        self.persisted = True
        return 3

    async def cleanup_project_final_retrieval_projections(
        self,
        *,
        project_id: str,
    ) -> int:
        self.cleanups.append(project_id)
        return 8


@pytest.mark.asyncio
async def test_clear_project_cleans_final_retrieval_projections() -> None:
    repository = FakeRepository()
    service = WorkbenchProjectClearService(repository)

    result = await service.clear_project(
        WorkbenchProjectClearCommand(project_id="project-1")
    )

    assert repository.persisted is True
    assert repository.cleanups == ["project-1"]
    assert result.runtime_publications_removed is True
    assert result.affected_documents == 3
