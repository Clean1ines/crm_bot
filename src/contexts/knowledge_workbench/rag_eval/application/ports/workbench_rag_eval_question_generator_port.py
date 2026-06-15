from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval import (
    GeneratedWorkbenchRagEvalQuestion,
)


class WorkbenchRagEvalQuestionGeneratorPort(Protocol):
    async def generate_questions_for_entry(
        self,
        *,
        claim: str,
        possible_questions: tuple[str, ...],
        exclusion_scope: str | None,
        evidence_block: str | None,
        triples: tuple[Mapping[str, object], ...],
    ) -> tuple[GeneratedWorkbenchRagEvalQuestion, ...]: ...
