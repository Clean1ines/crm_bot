from pathlib import Path


PORT = Path("src/application/ports/faq_workbench_registry_merge_generator.py")
GENERATOR = Path("src/infrastructure/llm/faq_workbench_registry_merge_generator.py")
PROMPT = Path("src/agent/prompts/faq_surface_registry_merge.ru.txt")


def test_registry_merge_node_is_fact_registry_canonicalization_contract() -> None:
    port = PORT.read_text(encoding="utf-8")
    generator = GENERATOR.read_text(encoding="utf-8")
    prompt = PROMPT.read_text(encoding="utf-8")

    assert "fact_registry" in port
    assert "registry_update_summary" in port
    assert "fact_registry" in generator
    assert "registry_update_summary" in generator
    assert "fact_registry" in prompt
    assert "NODE: faq_fact_registry_canonicalization" in prompt

    forbidden = (
        "previous_fact_registry",
        "RegistryUpdateProposal",
        "RegistryUpdateOperation",
        "RegistryUpdateProposalStatus",
        "parse_registry_updates_payload",
        "registry_updates[]",
        "claim_inputs",
        "candidate_fact_sets",
        "match_context",
    )

    for token in forbidden:
        assert token not in port
        assert token not in generator
        assert token not in prompt
