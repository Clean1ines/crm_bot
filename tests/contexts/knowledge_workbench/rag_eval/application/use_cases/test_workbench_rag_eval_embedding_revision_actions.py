from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval_embedding_revision import (
    WorkbenchRagEvalEmbeddingRevisionReadModel,
    WorkbenchRagEvalEmbeddingRevisionStatus,
)
from src.contexts.knowledge_workbench.rag_eval.application.use_cases.accept_workbench_rag_eval_embedding_revision import (
    AcceptWorkbenchRagEvalEmbeddingRevision,
    AcceptWorkbenchRagEvalEmbeddingRevisionCommand,
)
from src.contexts.knowledge_workbench.rag_eval.application.use_cases.rollback_workbench_rag_eval_embedding_revision import (
    RollbackWorkbenchRagEvalEmbeddingRevision,
    RollbackWorkbenchRagEvalEmbeddingRevisionCommand,
)


NOW = datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc)


@dataclass(slots=True)
class FakeRevisionActionRepository:
    accepted_call: tuple[str, str, datetime] | None = None
    rolled_back_call: tuple[str, str, datetime] | None = None

    async def accept_embedding_revision(
        self,
        *,
        project_id: str,
        revision_id: str,
        accepted_at: datetime,
    ) -> WorkbenchRagEvalEmbeddingRevisionReadModel:
        self.accepted_call = (project_id, revision_id, accepted_at)
        return _revision(
            status=WorkbenchRagEvalEmbeddingRevisionStatus.ACCEPTED,
            accepted_at=accepted_at,
        )

    async def rollback_embedding_revision(
        self,
        *,
        project_id: str,
        revision_id: str,
        rolled_back_at: datetime,
    ) -> WorkbenchRagEvalEmbeddingRevisionReadModel:
        self.rolled_back_call = (project_id, revision_id, rolled_back_at)
        return _revision(
            status=WorkbenchRagEvalEmbeddingRevisionStatus.ROLLED_BACK,
            rolled_back_at=rolled_back_at,
        )


async def test_accept_revision_use_case_delegates_to_atomic_repository_action() -> None:
    repository = FakeRevisionActionRepository()

    result = await AcceptWorkbenchRagEvalEmbeddingRevision(repository).execute(
        AcceptWorkbenchRagEvalEmbeddingRevisionCommand(
            project_id=" project-1 ",
            revision_id=" revision-1 ",
            now=NOW,
        )
    )

    assert repository.accepted_call == ("project-1", "revision-1", NOW)
    assert result.status is WorkbenchRagEvalEmbeddingRevisionStatus.ACCEPTED
    assert result.accepted_at == NOW


async def test_rollback_revision_use_case_delegates_to_atomic_repository_action() -> (
    None
):
    repository = FakeRevisionActionRepository()

    result = await RollbackWorkbenchRagEvalEmbeddingRevision(repository).execute(
        RollbackWorkbenchRagEvalEmbeddingRevisionCommand(
            project_id=" project-1 ",
            revision_id=" revision-1 ",
            now=NOW,
        )
    )

    assert repository.rolled_back_call == ("project-1", "revision-1", NOW)
    assert result.status is WorkbenchRagEvalEmbeddingRevisionStatus.ROLLED_BACK
    assert result.rolled_back_at == NOW


def _revision(
    *,
    status: WorkbenchRagEvalEmbeddingRevisionStatus,
    accepted_at: datetime | None = None,
    rolled_back_at: datetime | None = None,
) -> WorkbenchRagEvalEmbeddingRevisionReadModel:
    return WorkbenchRagEvalEmbeddingRevisionReadModel(
        revision_id="revision-1",
        project_id="project-1",
        runtime_entry_id="entry-1",
        source_rag_eval_run_id="run-1",
        promotion_ids=("promotion-1",),
        status=status,
        previous_promoted_questions=("Old?",),
        new_promoted_questions=("Old?", "New?"),
        created_at=NOW,
        accepted_at=accepted_at,
        regression_failed_at=None,
        rolled_back_at=rolled_back_at,
    )
