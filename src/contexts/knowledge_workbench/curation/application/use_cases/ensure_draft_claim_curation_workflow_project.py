from __future__ import annotations

from dataclasses import dataclass

from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_saga_ports import (
    KnowledgeExtractionSagaStateRepositoryPort,
)


class DraftClaimCurationWorkflowNotFoundError(LookupError):
    pass


class DraftClaimCurationWorkflowProjectMismatchError(PermissionError):
    pass


@dataclass(frozen=True, slots=True)
class DraftClaimCurationWorkflowProject:
    workflow_run_id: str
    project_id: str
    source_document_ref: str

    def __post_init__(self) -> None:
        _require_non_empty(self.workflow_run_id, "workflow_run_id")
        _require_non_empty(self.project_id, "project_id")
        _require_non_empty(self.source_document_ref, "source_document_ref")


@dataclass(frozen=True, slots=True)
class EnsureDraftClaimCurationWorkflowProject:
    state_repository: KnowledgeExtractionSagaStateRepositoryPort

    async def execute(
        self,
        *,
        workflow_run_id: str,
        expected_project_id: str,
    ) -> DraftClaimCurationWorkflowProject:
        _require_non_empty(workflow_run_id, "workflow_run_id")
        _require_non_empty(expected_project_id, "expected_project_id")

        state = await self.state_repository.load_workflow_state(workflow_run_id)
        if state is None:
            raise DraftClaimCurationWorkflowNotFoundError(
                "knowledge extraction workflow not found"
            )
        if state.project_id != expected_project_id:
            raise DraftClaimCurationWorkflowProjectMismatchError(
                "workflow does not belong to project"
            )
        return DraftClaimCurationWorkflowProject(
            workflow_run_id=state.workflow_run_id,
            project_id=state.project_id,
            source_document_ref=state.source_document_ref,
        )


def _require_non_empty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty")
