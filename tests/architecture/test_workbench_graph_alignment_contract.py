from pathlib import Path


DOMAIN = Path("src/domain/project_plane/knowledge_workbench/graph_alignment.py")
REGISTRY_MERGE_PORT = Path("src/application/ports/faq_workbench_registry_merge_generator.py")


def test_graph_alignment_domain_remains_candidate_bounded_and_persistence_free() -> None:
    source = DOMAIN.read_text(encoding="utf-8")

    required = (
        "class CandidateFact",
        "class CandidateFactSet",
        "class GraphAlignmentDecision",
        "class GraphAlignmentDecisionType",
        "max_candidates: int = 20",
        'NEW = "new"',
        'CONTRADICTS = "contradicts"',
        'SAME_MEANING = "same_meaning"',
    )
    for marker in required:
        assert marker in source

    forbidden = (
        "CREATE TABLE",
        "INSERT INTO",
        "asyncpg",
        "LLM",
    )
    for marker in forbidden:
        assert marker not in source


def test_registry_merge_port_no_longer_accepts_graph_alignment_candidate_sets_directly() -> None:
    source = REGISTRY_MERGE_PORT.read_text(encoding="utf-8")

    assert "canonicalization_unit: LocalClaimCanonicalizationUnit" in source
    assert "canonical_facts: tuple[CanonicalFact, ...]" in source

    stale_markers = (
        "claim_inputs: tuple[dict[str, JsonValue], ...]",
        "CandidateFactSet",
        "candidate_fact_sets: tuple[CandidateFactSet, ...] = ()",
    )
    for marker in stale_markers:
        assert marker not in source
