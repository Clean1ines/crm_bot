from __future__ import annotations

from pathlib import Path


PARALLEL_HANDLER = Path(
    "src/infrastructure/queue/handlers/workbench_parallel_processing.py"
)
RETIRED_DOCUMENT_HANDLER = Path(
    "src/infrastructure/queue/handlers/workbench_document.py"
)
PROMPT_A_GENERATOR = Path(
    "src/infrastructure/llm/faq_workbench_claim_observations_generator.py"
)
PROMPT_C_GENERATOR = Path(
    "src/infrastructure/llm/faq_workbench_registry_merge_generator.py"
)
PARALLEL_COMPOSITION = Path(
    "src/interfaces/composition/faq_workbench_parallel_processing.py"
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_parallel_workbench_handler_uses_best_groq_json_factory_explicitly() -> None:
    source = _read(PARALLEL_HANDLER)

    assert "make_workbench_claim_observations_generator" in source
    assert "GroqLlmJsonInvocationAdapter.create_default()" in source
    assert "FaqWorkbenchClaimObservationsGeneratorConfig" in source
    assert "faq_surface_claim_observations.ru.txt" in source

    assert "knowledge_surface_compiler" not in source
    assert "knowledge_surface_parallel_graph_compiler" not in source
    assert "FaqWorkbenchSectionFindingsRunner" not in source


def test_retired_workbench_document_handler_does_not_own_groq_or_prompt_wiring() -> None:
    source = _read(RETIRED_DOCUMENT_HANDLER)

    assert "legacy process_workbench_document task is retired" in source
    assert "GroqLlmJsonInvocationAdapter" not in source
    assert "make_workbench_claim_observations_generator" not in source
    assert "FaqWorkbenchClaimObservationsGenerator" not in source
    assert "FaqWorkbenchRegistryMergeGenerator" not in source


def test_groq_is_wired_only_at_infrastructure_composition_boundary() -> None:
    parallel_handler_source = _read(PARALLEL_HANDLER)
    composition_source = _read(PARALLEL_COMPOSITION)
    prompt_a_source = _read(PROMPT_A_GENERATOR)
    prompt_c_source = _read(PROMPT_C_GENERATOR)

    assert (
        "from src.infrastructure.llm.groq_llm_json_invocation import"
        in parallel_handler_source
    )
    assert "GroqLlmJsonInvocationAdapter.create_default()" in parallel_handler_source
    assert "GroqLlmJsonInvocationAdapter.create_default()" in composition_source

    assert "GroqLlmJsonInvocationAdapter.create_default()" not in prompt_a_source
    assert "GroqLlmJsonInvocationAdapter.create_default()" not in prompt_c_source


def test_prompt_generators_depend_on_llm_json_invocation_port_not_groq_directly() -> None:
    prompt_a_source = _read(PROMPT_A_GENERATOR)
    prompt_c_source = _read(PROMPT_C_GENERATOR)

    for source in (prompt_a_source, prompt_c_source):
        assert "LlmJsonInvocationPort" in source
        assert "LlmJsonInvocationRequest" in source
        assert "GroqLlmJsonInvocationAdapter" not in source
        assert "configured_groq_api_keys" not in source
        assert "RotatingAsyncGroq" not in source


def test_parallel_handler_does_not_resurrect_old_prompt_c_section_merge_shape() -> None:
    source = _read(PARALLEL_HANDLER)

    assert "claim_observations_runner" in source
    assert "DefaultClaimObservationsRunner" in source
    assert "make_workbench_canonicalization_barrier_service_from_repository" in source

    assert "claim_inputs" not in source
    assert "candidate_fact_sets" not in source
    assert "match_context" not in source
    assert "ProcessMarkdownDocumentCommand" not in source


def test_parallel_composition_keeps_prompt_a_and_prompt_c_boundaries_separate() -> None:
    source = _read(PARALLEL_COMPOSITION)

    assert "claim_observations_runner" in source
    assert "make_workbench_canonicalization_barrier_service_from_repository" in source
    assert "FaqWorkbenchRegistryMergeGenerator" in source

    section_factory_source = source.split(
        "def make_workbench_section_processor_from_repository",
        1,
    )[1].split(
        "def make_workbench_canonicalization_barrier_service_from_repository",
        1,
    )[0]

    assert "claim_observations_runner" in section_factory_source
    assert "FaqWorkbenchRegistryMergeGenerator" not in section_factory_source
    assert "FaqWorkbenchCanonicalizationBarrierService" not in section_factory_source
