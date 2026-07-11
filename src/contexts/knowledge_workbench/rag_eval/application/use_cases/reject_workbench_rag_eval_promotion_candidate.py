from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval import (
    WorkbenchRagEvalPromotionCandidateDetails,
)
from src.contexts.knowledge_workbench.rag_eval.application.ports.workbench_rag_eval_repository_port import (
    WorkbenchRagEvalRepositoryPort,
)


@dataclass(frozen=True, slots=True)
class RejectWorkbenchRagEvalPromotionCandidateCommand:
    promotion_id: str
    run_id: str
    project_id: str
    now: datetime
    reason: str


@dataclass(frozen=True, slots=True)
class RejectWorkbenchRagEvalPromotionCandidate:
    repository: WorkbenchRagEvalRepositoryPort

    async def execute(
        self,
        command: RejectWorkbenchRagEvalPromotionCandidateCommand,
    ) -> WorkbenchRagEvalPromotionCandidateDetails:
        return await self.repository.reject_promotion_candidate(
            promotion_id=_require_text(command.promotion_id, "promotion_id"),
            run_id=_require_text(command.run_id, "run_id"),
            project_id=_require_text(command.project_id, "project_id"),
            reviewed_at=command.now,
            reason=_require_text(command.reason, "reason"),
        )


def _require_text(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must be non-empty")
    return normalized
