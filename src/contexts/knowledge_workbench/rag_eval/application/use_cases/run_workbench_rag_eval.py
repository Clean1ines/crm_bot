"""Retired synchronous RAG Eval boundary.

The production workflow is ``StartWorkbenchRagEvalV2`` plus the durable
execution runtime and production ``SearchPublishedWorkbenchRuntime``. This
compatibility symbol remains only for old imports.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval import (
    WorkbenchRagEvalSummary,
)


class WorkbenchRagEvalNoPublishedEntriesError(LookupError):
    """Compatibility exception retained for callers of the retired API."""


@dataclass(frozen=True, slots=True)
class RunWorkbenchRagEval:
    """Fail-fast compatibility symbol; never a production fallback."""

    async def execute(
        self,
        *,
        project_id: str,
        publication_id: str | None,
        source_document_ref: str | None,
        top_k: int | None,
        max_entries: int,
        now: datetime,
        allow_degraded_llama_instant: bool = False,
    ) -> WorkbenchRagEvalSummary:
        del project_id, publication_id, source_document_ref, top_k
        del max_entries, now, allow_degraded_llama_instant
        raise RuntimeError(
            "RunWorkbenchRagEval is retired; use StartWorkbenchRagEvalV2 "
            "and the durable execution runtime"
        )
