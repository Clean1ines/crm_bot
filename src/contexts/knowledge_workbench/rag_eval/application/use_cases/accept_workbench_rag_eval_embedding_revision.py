from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval_embedding_revision import (
    WorkbenchRagEvalEmbeddingRevisionReadModel,
)
from src.contexts.knowledge_workbench.rag_eval.application.ports.workbench_rag_eval_repository_port import (
    WorkbenchRagEvalRepositoryPort,
)


@dataclass(frozen=True, slots=True)
class AcceptWorkbenchRagEvalEmbeddingRevisionCommand:
    project_id: str
    revision_id: str
    now: datetime


@dataclass(frozen=True, slots=True)
class AcceptWorkbenchRagEvalEmbeddingRevision:
    repository: WorkbenchRagEvalRepositoryPort

    async def execute(
        self,
        command: AcceptWorkbenchRagEvalEmbeddingRevisionCommand,
    ) -> WorkbenchRagEvalEmbeddingRevisionReadModel:
        return await self.repository.accept_embedding_revision(
            project_id=_require_text(command.project_id, "project_id"),
            revision_id=_require_text(command.revision_id, "revision_id"),
            accepted_at=command.now,
        )


def _require_text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be non-empty")
    return normalized
