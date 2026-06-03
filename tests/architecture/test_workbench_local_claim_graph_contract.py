from pathlib import Path

DOMAIN = Path("src/domain/project_plane/knowledge_workbench/local_claim_graph.py")
GENERATOR = Path("src/infrastructure/llm/faq_workbench_claim_observations_generator.py")
SERVICE = Path("src/application/services/faq_workbench_claim_observations_service.py")


def test_local_claim_graph_domain_is_extraction_only() -> None:
    source = DOMAIN.read_text(encoding="utf-8")

    assert "class LocalClaimGraph" in source
    assert "LocalClaim" in source
    assert "LocalClaimTriple" in source
    assert "LocalEvidenceMention" in source
    assert "LocalClaimRelation" in source
    assert "local_claim_graph_from_claim_observations_payload" in source

    assert "relation_to_known_claim" not in source
    assert "suggested_registry_action" not in source
    assert "known_facts" not in source


def test_claim_observations_payload_exposes_local_graph_material_only() -> None:
    source = GENERATOR.read_text(encoding="utf-8")

    for token in (
        '"local_ref"',
        '"claim"',
        '"claim_kind"',
        '"granularity"',
        '"triples"',
        '"evidence_block"',
        '"possible_questions"',
        '"scope"',
        '"exclusion_scope"',
        '"local_relations"',
        '"confidence"',
    ):
        assert token in source

    assert '"relation_to_known_claim"' not in source
    assert '"suggested_registry_action"' not in source
    assert '"known_facts"' not in source


def test_claim_observations_artifact_remains_existing_source_payload() -> None:
    source = SERVICE.read_text(encoding="utf-8")

    assert '"claim_observations": list(claim_observations)' in source
    assert '"claim_observation_count": len(claim_observations)' in source
