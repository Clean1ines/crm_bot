from pathlib import Path

GENERATOR = Path("src/infrastructure/llm/faq_workbench_claim_observations_generator.py")


def test_generator_build_prompt_sends_only_source_unit() -> None:
    source = GENERATOR.read_text(encoding="utf-8")

    assert "def build_prompt(" in source
    assert "INPUT_SOURCE_UNIT_JSON" in source
    assert "INPUT_KNOWN_FACTS_JSON" not in source
    assert "known_facts" not in source


def test_generator_parser_accepts_local_claim_graph_fields_only() -> None:
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

    assert "relation_to_known_claim" not in source
    assert "suggested_registry_action" not in source
