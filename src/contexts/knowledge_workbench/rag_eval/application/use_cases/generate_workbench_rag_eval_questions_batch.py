from __future__ import annotations

from dataclasses import dataclass

from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval import (
    GeneratedWorkbenchRagEvalQuestion,
)
from src.contexts.knowledge_workbench.retrieval.application.models.published_workbench_retrieval import (
    PublishedWorkbenchRetrievalResult,
)


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalGeneratedEntryQuestions:
    entry: PublishedWorkbenchRetrievalResult
    generated_questions: tuple[GeneratedWorkbenchRagEvalQuestion, ...]


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalQuestionGenerationBatchExecutor:
    """Retired sync API placeholder.

    RAG Eval V2 schedules one question-generation work item per published runtime
    entry and executes it through Execution Runtime. This class remains only so
    older import sites fail with an explicit migration error instead of silently
    bypassing the canonical workflow.
    """

    async def generate_for_entries(
        self,
        *,
        entries: tuple[PublishedWorkbenchRetrievalResult, ...],
        allow_degraded_llama_instant: bool,
    ) -> tuple[WorkbenchRagEvalGeneratedEntryQuestions, ...]:
        del entries, allow_degraded_llama_instant
        raise RuntimeError(
            "Workbench RAG Eval question generation is retired on the sync path; "
            "use StartWorkbenchRagEvalV2 and Execution Runtime work items."
        )
