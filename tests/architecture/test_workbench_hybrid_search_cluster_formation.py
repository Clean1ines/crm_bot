from pathlib import Path


DOMAIN = Path("src/domain/project_plane/knowledge_workbench/local_claim_retrieval.py")
SERVICE = Path("src/application/services/faq_workbench_local_claim_retrieval_service.py")


def test_local_claim_retrieval_domain_contains_hybrid_search_cluster_formation_layer() -> None:
    source = DOMAIN.read_text(encoding="utf-8")

    required = (
        "class LocalClaimHybridSearchHit",
        "class LocalClaimHybridSearchTrace",
        "def build_local_claim_hybrid_similarity_edges",
        "def build_local_claim_hybrid_similarity_edges_with_trace",
        "def search_local_claim_hybrid_candidates",
        "class _HybridLocalClaimIndex",
        "token_postings",
        "ngram_postings",
        "search_text_token_overlap",
        "search_text_char_ngram_overlap",
        "controlled_predicate_overlap",
        "candidate_limit_per_document",
    )
    for marker in required:
        assert marker in source


def test_local_claim_retrieval_service_uses_hybrid_edges_when_service_exists() -> None:
    if not SERVICE.exists():
        return

    source = SERVICE.read_text(encoding="utf-8")

    assert "build_local_claim_hybrid_similarity_edges" in source
    assert "build_local_claim_similarity_edges(" not in source
