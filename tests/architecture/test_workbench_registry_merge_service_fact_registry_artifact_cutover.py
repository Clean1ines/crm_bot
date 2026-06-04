from pathlib import Path


SERVICE = Path("src/application/services/faq_workbench_registry_merge_service.py")


def test_registry_merge_service_persists_fact_registry_artifact_not_old_proposals() -> (
    None
):
    source = SERVICE.read_text(encoding="utf-8")

    assert "fact_registry" in source
    assert "registry_update_summary" in source
    assert "canonical_fact_count" in source
    assert "fact_relation_count" in source
    assert "fact_registry_canonicalization" in source

    forbidden = (
        "RegistryUpdateProposal",
        "create_registry_update_proposals",
        "proposal_count",
        "generation_result.proposals",
        "registry merge proposal",
        "proposals:",
    )

    for token in forbidden:
        assert token not in source
