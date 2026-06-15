from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ProductionRetrievalMode(StrEnum):
    """Runtime-safety mode for project knowledge retrieval."""

    RUNTIME = "runtime"
    RUNTIME_EQUIVALENT_PREVIEW = "runtime_equivalent_preview"
    LEXICAL_DEBUG = "lexical_debug"


class ProductionRetrievalCaller(StrEnum):
    """Known callers that need an explicit production-retrieval policy."""

    ASSISTANT_RUNTIME = "assistant_runtime"
    KNOWLEDGE_PREVIEW = "knowledge_preview"
    RAG_EVAL = "rag_eval"
    CURATION_DEBUG = "curation_debug"


@dataclass(frozen=True, slots=True)
class ProductionRetrievalPolicy:
    """Domain-only retrieval policy for published Workbench runtime entries."""

    caller: ProductionRetrievalCaller
    mode: ProductionRetrievalMode
    runtime_equivalent: bool
    production_safe: bool
    diagnostic: bool
    source_name: str
    reason: str

    @property
    def requires_workbench_runtime(self) -> bool:
        return self.production_safe and self.runtime_equivalent


def resolve_production_retrieval_policy(
    caller: ProductionRetrievalCaller,
) -> ProductionRetrievalPolicy:
    """Resolve the retrieval policy for a caller without touching infrastructure."""

    if caller == ProductionRetrievalCaller.ASSISTANT_RUNTIME:
        return ProductionRetrievalPolicy(
            caller=caller,
            mode=ProductionRetrievalMode.RUNTIME,
            runtime_equivalent=True,
            production_safe=True,
            diagnostic=False,
            source_name="knowledge_workbench_runtime_retrieval_entries",
            reason="assistant runtime uses published Workbench runtime retrieval",
        )
    if caller == ProductionRetrievalCaller.KNOWLEDGE_PREVIEW:
        return ProductionRetrievalPolicy(
            caller=caller,
            mode=ProductionRetrievalMode.RUNTIME_EQUIVALENT_PREVIEW,
            runtime_equivalent=True,
            production_safe=True,
            diagnostic=False,
            source_name="knowledge_workbench_runtime_retrieval_entries",
            reason="knowledge preview must be equivalent to Workbench runtime retrieval",
        )
    if caller == ProductionRetrievalCaller.RAG_EVAL:
        return ProductionRetrievalPolicy(
            caller=caller,
            mode=ProductionRetrievalMode.RUNTIME_EQUIVALENT_PREVIEW,
            runtime_equivalent=True,
            production_safe=True,
            diagnostic=False,
            source_name="SearchPublishedWorkbenchRuntime",
            reason="Workbench RAG eval evaluates published Workbench runtime retrieval",
        )
    if caller == ProductionRetrievalCaller.CURATION_DEBUG:
        return ProductionRetrievalPolicy(
            caller=caller,
            mode=ProductionRetrievalMode.LEXICAL_DEBUG,
            runtime_equivalent=False,
            production_safe=False,
            diagnostic=True,
            source_name="workbench_runtime_lexical_debug",
            reason="curation debug is diagnostic-only, not runtime-equivalent",
        )
    raise ValueError(f"Unsupported production retrieval caller: {caller!r}")


__all__ = (
    "ProductionRetrievalCaller",
    "ProductionRetrievalMode",
    "ProductionRetrievalPolicy",
    "resolve_production_retrieval_policy",
)
