from __future__ import annotations

from pathlib import Path


SERVICE = Path("src/application/services/faq_workbench_claim_observations_service.py")
ORCH = Path(
    "src/application/services/faq_workbench_document_processing_orchestrator.py"
)
GENERATOR_PORT = Path(
    "src/application/ports/faq_workbench_claim_observations_generator.py"
)


def test_claim_observations_port_keeps_full_invocation_result() -> None:
    source = GENERATOR_PORT.read_text(encoding="utf-8")

    assert "invocation: LlmJsonInvocationResult" in source
    assert "raw_payload: JsonValue | None" in source
    assert "warnings: tuple[str, ...]" in source
    assert "metrics: dict[str, JsonValue]" in source


def test_orchestrator_passes_llm_metadata_to_claim_observations_service() -> None:
    source = ORCH.read_text(encoding="utf-8")

    assert "GeneratedClaimObservations" in source
    assert "ClaimObservationsLlmMetadata" in source
    assert "generation_result.invocation" in source
    assert "prompt_tokens=llm_metadata.prompt_tokens" in source
    assert "completion_tokens=llm_metadata.completion_tokens" in source
    assert "route_attempts=llm_metadata.route_attempts" in source
    assert "return generation_result.findings" not in source


def test_claim_observations_service_persists_raw_and_parsed_llm_artifacts() -> None:
    source = SERVICE.read_text(encoding="utf-8")

    assert "ProcessingNodeArtifactType.RAW_LLM_OUTPUT" in source
    assert "ProcessingNodeArtifactType.PARSED_LLM_OUTPUT" in source
    assert "route_attempts" in source
    assert "raw_text" in source
    assert "raw_payload" in source
    assert "invocation_status" in source


def test_claim_observations_node_run_records_model_provider_slot_and_tokens() -> None:
    source = SERVICE.read_text(encoding="utf-8")

    assert "model_provider=command.model_provider" in source
    assert "groq_key_slot=command.api_key_slot" in source
    assert "prompt_tokens=command.prompt_tokens" in source
    assert "completion_tokens=command.completion_tokens" in source
    assert "total_tokens=total_tokens" in source


def test_llm_metadata_persistence_stays_provider_agnostic_in_application() -> None:
    combined = SERVICE.read_text(encoding="utf-8") + ORCH.read_text(encoding="utf-8")

    forbidden = (
        "AsyncGroq",
        "GroqLlmJsonInvocationAdapter",
        "RotatingAsyncGroq",
        "GROQ_API_KEY",
        "knowledge_surface_compiler",
        "process_knowledge_upload",
        "AnswerCandidate",
        "CandidateCluster",
    )
    for marker in forbidden:
        assert marker not in combined
