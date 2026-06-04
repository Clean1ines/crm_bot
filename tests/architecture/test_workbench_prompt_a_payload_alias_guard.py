from pathlib import Path


GENERATOR = Path("src/infrastructure/llm/faq_workbench_claim_observations_generator.py")


def test_prompt_a_generator_accepts_claims_alias_but_persists_canonical_claim_observations() -> (
    None
):
    source = GENERATOR.read_text()

    assert "def _normalize_claim_observations_payload(" in source
    assert '"claims" in payload' in source
    assert 'normalized["claim_observations"] = normalized.pop("claims")' in source
    assert "raw_payload=normalized_payload" in source
    assert "parse_claim_observations_payload(normalized_payload)" in source


def test_prompt_a_parser_remains_canonical_after_alias_normalization() -> None:
    source = GENERATOR.read_text()

    parser_start = source.index("def parse_claim_observations_payload(")
    parser_end = source.index("def _parse_claim_observation(", parser_start)
    parser = source[parser_start:parser_end]

    assert 'payload.get("claim_observations")' in parser
    assert 'payload.get("claims")' not in parser
