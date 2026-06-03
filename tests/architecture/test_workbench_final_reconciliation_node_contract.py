from __future__ import annotations

from pathlib import Path


PORT = Path("src/application/ports/faq_workbench_final_reconciliation_generator.py")
GRAPH_CONTRACT = Path("src/application/workbench/processing_graph_contract.py")
ORCH = Path(
    "src/application/services/faq_workbench_document_processing_orchestrator.py"
)
MATERIALIZATION = Path(
    "src/application/services/faq_workbench_surface_materialization_service.py"
)
FINAL_RECONCILIATION_GENERATOR = Path(
    "src/infrastructure/llm/faq_workbench_final_reconciliation_generator.py"
)
FINAL_RECONCILIATION_SERVICE = Path(
    "src/application/services/faq_workbench_final_reconciliation_service.py"
)
QUEUE_HANDLER = Path("src/infrastructure/queue/handlers/workbench_document.py")


def _read(path: Path) -> str:
    assert path.exists(), f"missing expected source file: {path}"
    return path.read_text(encoding="utf-8")


def test_final_reconciliation_contract_stack_exists() -> None:
    port_source = _read(PORT)
    generator_source = _read(FINAL_RECONCILIATION_GENERATOR)
    service_source = _read(FINAL_RECONCILIATION_SERVICE)
    graph_source = _read(GRAPH_CONTRACT)

    assert "FaqWorkbenchFinalReconciliationGeneratorPort" in port_source
    assert "FaqWorkbenchFinalReconciliationGenerationCommand" in port_source
    assert "FaqWorkbenchFinalReconciliationGenerationResult" in port_source
    assert "FaqWorkbenchFinalReconciliationGenerationError" in port_source
    assert "FinalReconciliationAdvice" in port_source

    assert "class FaqWorkbenchFinalReconciliationGenerator" in generator_source
    assert "generate_final_reconciliation" in generator_source
    assert "parse_final_reconciliation_payload" in generator_source
    assert (
        'operation_name: str = "faq_surface_final_reconciliation"' in generator_source
    )
    assert 'route_purpose: str = "workbench_final_reconciliation"' in generator_source

    assert "class FaqWorkbenchFinalReconciliationService" in service_source
    assert "persist_final_reconciliation_output" in service_source
    assert "persist_final_reconciliation_generation_error" in service_source

    assert "FAQ_SURFACE_FINAL_RECONCILIATION_NODE" in graph_source
    assert '"final_reconciliation_suggestions"' in graph_source


def test_final_reconciliation_is_runtime_wired_as_advisory_node() -> None:
    orchestrator_source = _read(ORCH)
    handler_source = _read(QUEUE_HANDLER)

    assert "FaqWorkbenchFinalReconciliationGeneratorPort" in orchestrator_source
    assert "FaqWorkbenchFinalReconciliationService" in orchestrator_source
    assert "FaqWorkbenchFinalReconciliationGenerationCommand" in orchestrator_source
    assert "ProcessFinalReconciliationGenerationErrorCommand" in orchestrator_source
    assert "PersistFinalReconciliationNodeOutputCommand" in orchestrator_source
    assert "_persist_final_reconciliation_advice" in orchestrator_source
    assert "generate_final_reconciliation" in orchestrator_source
    assert "persist_final_reconciliation_output" in orchestrator_source
    assert "persist_final_reconciliation_generation_error" in orchestrator_source

    assert "make_workbench_final_reconciliation_generator" in handler_source
    assert (
        "final_reconciliation_generator=make_workbench_final_reconciliation_generator()"
        in handler_source
    )
    assert "FaqWorkbenchFinalReconciliationGenerationError," in handler_source


def test_final_reconciliation_runs_after_section_loop_and_before_materialization() -> (
    None
):
    orchestrator_source = _read(ORCH)

    markdown_processing_index = orchestrator_source.index("processed_sections,")
    first_final_index = orchestrator_source.index(
        "await self._persist_final_reconciliation_advice("
    )
    first_materialization_index = orchestrator_source.index(
        "_surface_materialization_service.materialize_surfaces("
    )

    assert markdown_processing_index < first_final_index < first_materialization_index

    second_final_index = orchestrator_source.index(
        "await self._persist_final_reconciliation_advice(",
        first_final_index + 1,
    )
    second_materialization_index = orchestrator_source.index(
        "_surface_materialization_service.materialize_surfaces(",
        first_materialization_index + 1,
    )

    assert second_final_index < second_materialization_index


def test_final_reconciliation_does_not_change_materialization_semantics_yet() -> None:
    materialization_source = _read(MATERIALIZATION)

    assert "final_reconciliation_suggestions" not in materialization_source
    assert "MaterializeRegistrySurfacesCommand" in materialization_source


def test_final_reconciliation_stack_is_advisory_and_does_not_mutate_registry() -> None:
    sources = {
        "port": _read(PORT),
        "generator": _read(FINAL_RECONCILIATION_GENERATOR),
        "service": _read(FINAL_RECONCILIATION_SERVICE),
        "orchestrator": _read(ORCH),
        "queue_handler": _read(QUEUE_HANDLER),
    }
    forbidden = (
        "RegistryUpdateAppliedBy.LLM_ADVISORY",
        "RegistryUpdateApplication(",
        "create_registry_update_applications",
        "create_registry_update_proposals",
        "upsert_question_registry_entries",
    )

    for source_name, source in sources.items():
        for marker in forbidden:
            assert marker not in source, f"{marker} leaked into {source_name}"

    assert "apply_findings_to_registry" not in _read(FINAL_RECONCILIATION_SERVICE)
    assert "apply_findings_to_registry" not in _read(FINAL_RECONCILIATION_GENERATOR)


def test_final_reconciliation_application_port_is_provider_agnostic() -> None:
    port_source = _read(PORT)

    forbidden = (
        "Groq",
        "AsyncGroq",
        "GroqLlmJsonInvocationAdapter",
        "src.infrastructure.llm",
        "GROQ_API_KEY",
    )
    for marker in forbidden:
        assert marker not in port_source
