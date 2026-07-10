from __future__ import annotations

from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind


WORKBENCH_RAG_EVAL_QUESTION_GENERATION_WORK_KIND = WorkKind(
    "workbench_rag_eval.question_generation",
)
WORKBENCH_RAG_EVAL_ADJUDICATION_WORK_KIND = WorkKind(
    "workbench_rag_eval.adjudication",
)


__all__ = [
    "WORKBENCH_RAG_EVAL_ADJUDICATION_WORK_KIND",
    "WORKBENCH_RAG_EVAL_QUESTION_GENERATION_WORK_KIND",
]
