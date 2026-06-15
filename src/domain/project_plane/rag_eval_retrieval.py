from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class RagEvalRetrievalMode(StrEnum):
    PRODUCTION_EQUIVALENT = "production_equivalent"
    VECTOR_DEBUG = "vector_debug"


@dataclass(frozen=True, slots=True)
class RagEvalRetrievalPolicy:
    mode: RagEvalRetrievalMode
    retrieval_path: str
    query_expansion_enabled: bool
    runtime_equivalent: bool
    diagnostic: bool
    description: str


def normalize_rag_eval_retrieval_mode(value: object) -> RagEvalRetrievalMode:
    text = str(value or "").strip().lower()
    if text in {"vector_debug", "embedding_debug"}:
        return RagEvalRetrievalMode.VECTOR_DEBUG
    return RagEvalRetrievalMode.PRODUCTION_EQUIVALENT


def resolve_rag_eval_retrieval_policy(
    mode: RagEvalRetrievalMode,
) -> RagEvalRetrievalPolicy:
    if mode == RagEvalRetrievalMode.VECTOR_DEBUG:
        return RagEvalRetrievalPolicy(
            mode=mode,
            retrieval_path="SearchPublishedWorkbenchRuntime.vector_debug",
            query_expansion_enabled=False,
            runtime_equivalent=False,
            diagnostic=True,
            description=(
                "Diagnostic embedding/vector-only retrieval over published Workbench "
                "runtime entries."
            ),
        )

    return RagEvalRetrievalPolicy(
        mode=RagEvalRetrievalMode.PRODUCTION_EQUIVALENT,
        retrieval_path="SearchPublishedWorkbenchRuntime",
        query_expansion_enabled=True,
        runtime_equivalent=True,
        diagnostic=False,
        description=(
            "Production-equivalent retrieval over published Workbench runtime entries "
            "and runtime entry embeddings."
        ),
    )


def rag_eval_retrieval_metadata(policy: RagEvalRetrievalPolicy) -> dict[str, object]:
    return {
        "retrieval_mode": policy.mode.value,
        "retrieval_path": policy.retrieval_path,
        "query_expansion_enabled": policy.query_expansion_enabled,
        "runtime_equivalent": policy.runtime_equivalent,
        "diagnostic": policy.diagnostic,
    }


__all__ = (
    "RagEvalRetrievalMode",
    "RagEvalRetrievalPolicy",
    "normalize_rag_eval_retrieval_mode",
    "resolve_rag_eval_retrieval_policy",
    "rag_eval_retrieval_metadata",
)
