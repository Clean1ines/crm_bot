from __future__ import annotations

import hashlib
import math

from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval import (
    WorkbenchRagEvalQuestionRole,
)


class WorkbenchRagEvalQuestionRolePolicy:
    def assign(
        self, *, entry_id: str, question_ids: tuple[str, ...]
    ) -> dict[str, WorkbenchRagEvalQuestionRole]:
        if not entry_id.strip() or not question_ids:
            raise ValueError("entry_id and question_ids must be non-empty")
        if len(set(question_ids)) != len(question_ids):
            raise ValueError("question_ids must be unique")
        holdout_count = max(1, math.ceil(len(question_ids) * 0.2))
        ordered = sorted(
            question_ids,
            key=lambda question_id: hashlib.sha256(
                f"{entry_id}:{question_id}".encode()
            ).hexdigest(),
        )
        holdouts = frozenset(ordered[:holdout_count])
        return {
            question_id: WorkbenchRagEvalQuestionRole.HOLDOUT
            if question_id in holdouts
            else WorkbenchRagEvalQuestionRole.BASELINE
            for question_id in question_ids
        }

    def promotion_eligible(
        self, *, role: WorkbenchRagEvalQuestionRole, generated_eligible: bool
    ) -> bool:
        return generated_eligible and role is WorkbenchRagEvalQuestionRole.BASELINE
