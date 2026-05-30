from src.domain.project_plane.rag_eval_retrieval import (
    RagEvalRetrievalMode,
    normalize_rag_eval_retrieval_mode,
    rag_eval_retrieval_metadata,
    resolve_rag_eval_retrieval_policy,
)


def test_production_equivalent_policy_is_runtime_equivalent() -> None:
    policy = resolve_rag_eval_retrieval_policy(
        RagEvalRetrievalMode.PRODUCTION_EQUIVALENT
    )

    assert policy.runtime_equivalent is True
    assert policy.diagnostic is False
    assert policy.query_expansion_enabled is True
    assert policy.retrieval_path == "production_rag_service.search_with_expansion"
    assert rag_eval_retrieval_metadata(policy)["retrieval_mode"] == (
        "production_equivalent"
    )


def test_vector_debug_policy_is_diagnostic_vector_only() -> None:
    policy = resolve_rag_eval_retrieval_policy(RagEvalRetrievalMode.VECTOR_DEBUG)

    assert policy.runtime_equivalent is False
    assert policy.diagnostic is True
    assert policy.query_expansion_enabled is False
    assert policy.retrieval_path == "knowledge_retrieval_surface.vector_only"


def test_embedding_debug_alias_normalizes_to_vector_debug() -> None:
    assert normalize_rag_eval_retrieval_mode("embedding_debug") == (
        RagEvalRetrievalMode.VECTOR_DEBUG
    )
    assert normalize_rag_eval_retrieval_mode(None) == (
        RagEvalRetrievalMode.PRODUCTION_EQUIVALENT
    )
