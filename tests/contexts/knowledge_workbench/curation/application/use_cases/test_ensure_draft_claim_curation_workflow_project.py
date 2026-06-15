from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_saga_state import (
    KnowledgeExtractionPhaseKey,
    KnowledgeExtractionWorkflowState,
    KnowledgeExtractionWorkflowStatus,
)
from src.contexts.knowledge_workbench.curation.application.use_cases.ensure_draft_claim_curation_workflow_project import (
    DraftClaimCurationWorkflowNotFoundError,
    DraftClaimCurationWorkflowProjectMismatchError,
    EnsureDraftClaimCurationWorkflowProject,
)


def _now() -> datetime:
    return datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)


def _workflow_state(
    *, project_id: str = "project-1"
) -> KnowledgeExtractionWorkflowState:
    return KnowledgeExtractionWorkflowState(
        workflow_run_id="workflow-1",
        project_id=project_id,
        source_document_ref="source-document:project-1:abc",
        status=KnowledgeExtractionWorkflowStatus.RUNNING,
        current_phase=KnowledgeExtractionPhaseKey.FINAL_KNOWLEDGE_PREPARED,
        created_at=_now(),
        updated_at=_now(),
    )


@dataclass(slots=True)
class FakeSagaStateRepository:
    state: KnowledgeExtractionWorkflowState | None

    async def load_workflow_state(
        self,
        workflow_run_id: str,
    ) -> KnowledgeExtractionWorkflowState | None:
        assert workflow_run_id == "workflow-1"
        return self.state


@pytest.mark.asyncio
async def test_missing_workflow_state_raises_not_found() -> None:
    with pytest.raises(DraftClaimCurationWorkflowNotFoundError):
        await EnsureDraftClaimCurationWorkflowProject(
            state_repository=FakeSagaStateRepository(state=None),
        ).execute(
            workflow_run_id="workflow-1",
            expected_project_id="project-1",
        )


@pytest.mark.asyncio
async def test_project_mismatch_raises_project_mismatch() -> None:
    with pytest.raises(DraftClaimCurationWorkflowProjectMismatchError):
        await EnsureDraftClaimCurationWorkflowProject(
            state_repository=FakeSagaStateRepository(
                state=_workflow_state(project_id="project-2")
            ),
        ).execute(
            workflow_run_id="workflow-1",
            expected_project_id="project-1",
        )


@pytest.mark.asyncio
async def test_matching_workflow_returns_authoritative_source_document_ref() -> None:
    result = await EnsureDraftClaimCurationWorkflowProject(
        state_repository=FakeSagaStateRepository(state=_workflow_state()),
    ).execute(
        workflow_run_id="workflow-1",
        expected_project_id="project-1",
    )

    assert result.workflow_run_id == "workflow-1"
    assert result.project_id == "project-1"
    assert result.source_document_ref == "source-document:project-1:abc"
