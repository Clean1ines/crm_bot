from pathlib import Path

PORT = Path("src/application/ports/faq_workbench_claim_observations_generator.py")
PROMPT = Path("src/agent/prompts/faq_surface_claim_observations.ru.txt")
GENERATOR = Path("src/infrastructure/llm/faq_workbench_claim_observations_generator.py")


def test_claim_observations_port_keeps_extraction_vocabulary() -> None:
    source = PORT.read_text(encoding="utf-8")

    assert "claim_observations" in source
    assert "source_unit -> local claims/local graph" in source
    assert "source_unit + known_facts" not in source
    assert "known_facts" not in source
    assert "relation_to_known_claim" not in source
    assert "suggested_registry_action" not in source


def test_prompt_a_is_extraction_only_local_claim_graph_contract() -> None:
    source = PROMPT.read_text(encoding="utf-8")

    assert "NODE: faq_claim_observations" in source
    assert "section/source_unit → local claims/local graph" in source
    assert "claim_observations" in source
    assert "triples" in source
    assert "possible_questions" in source
    assert "scope" in source
    assert "exclusion_scope" in source
    assert "local_relations" in source
    assert "confidence" in source

    assert "known_facts" not in source
    assert "INPUT_KNOWN_FACTS_JSON" not in source
    assert "relation_to_known_claim" not in source
    assert "suggested_registry_action" not in source


def test_infra_generator_does_not_prompt_with_registry_facts() -> None:
    source = GENERATOR.read_text(encoding="utf-8")

    assert "parse_claim_observations_payload" in source
    assert "INPUT_SOURCE_UNIT_JSON" in source
    assert "INPUT_KNOWN_FACTS_JSON" not in source
    assert "known_facts" not in source
    assert "relation_to_known_claim" not in source
    assert "suggested_registry_action" not in source
