from __future__ import annotations

from pathlib import Path


PORT = Path("src/application/ports/faq_workbench_claim_observations_generator.py")
GENERATOR = Path("src/infrastructure/llm/faq_workbench_claim_observations_generator.py")
def test_claim_observations_generator_port_returns_metadata_result_not_plain_tuple() -> (
    None
):
    source = PORT.read_text(encoding="utf-8")

    assert "class FaqWorkbenchClaimObservationsGenerationResult" in source
    assert "invocation: LlmJsonInvocationResult" in source
    assert "raw_payload: JsonValue | None" in source
    assert ") -> FaqWorkbenchClaimObservationsGenerationResult" in source
    assert ") -> tuple[ParsedSectionFinding" not in source


def test_claim_observations_generation_contract_is_provider_agnostic() -> None:
    source = PORT.read_text(encoding="utf-8")

    forbidden = (
        "Groq",
        "AsyncGroq",
        "GROQ_API_KEY",
        "RotatingAsyncGroq",
        "GroqLlmJsonInvocationAdapter",
    )
    for marker in forbidden:
        assert marker not in source


def test_infra_generator_preserves_invocation_result_and_payload_metadata() -> None:
    source = GENERATOR.read_text(encoding="utf-8")

    assert "FaqWorkbenchClaimObservationsGenerationResult" in source
    assert "invocation=result" in source
    assert "raw_payload=result.parsed_json" in source
    assert "warnings=self._warnings_from_payload(result.parsed_json)" in source
    assert "metrics=self._metrics_from_payload(result.parsed_json)" in source


def test_first_section_llm_entrypoint_now_uses_claim_observation_contract() -> None:
    port_source = PORT.read_text(encoding="utf-8")
    generator_source = GENERATOR.read_text(encoding="utf-8")

    assert "claim_observations" in port_source
    assert "ClaimObservation" in port_source
    assert "FaqWorkbenchClaimObservationsGenerationResult" in generator_source

    # The retired sequential orchestrator is no longer the production guard for
    # the first section LLM node.
    assert "return generation_result.findings" not in port_source
