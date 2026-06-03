from pathlib import Path


GENERATOR = Path("src/infrastructure/llm/faq_workbench_claim_observations_generator.py")


def test_first_section_infra_generator_parses_claim_observations_not_surface_findings() -> None:
    source = GENERATOR.read_text(encoding="utf-8")

    assert "parse_claim_observations_payload" in source
    assert 'payload.get("claim_observations")' in source
    assert "claim_observations=claim_observations" in source
    assert "INPUT_KNOWN_FACTS_JSON" in source
    assert "INPUT_SOURCE_UNIT_JSON" in source

    forbidden = (
        "ParsedSectionFinding",
        'payload.get("findings")',
        "parse_findings_payload",
        "_parse_finding",
        "SectionFindingAction",
        "SurfaceKind",
        "canonical_question",
        "answer_delta",
        "surface_key",
        "target_surface_key",
        "local_surface_key",
        "evidence_quotes",
    )

    for token in forbidden:
        assert token not in source
