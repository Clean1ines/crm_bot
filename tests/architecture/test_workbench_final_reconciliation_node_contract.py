from __future__ import annotations

from pathlib import Path


FINAL_RECONCILIATION_SERVICE = Path(
    "src/application/services/faq_workbench_final_reconciliation_service.py"
)
FINAL_RECONCILIATION_GENERATOR = Path(
    "src/infrastructure/llm/faq_workbench_final_reconciliation_generator.py"
)
OLD_SEQUENTIAL_ORCHESTRATOR = Path(
    "src/application/services/faq_workbench_document_processing_orchestrator.py"
)
OLD_SURFACE_MATERIALIZATION = Path(
    "src/application/services/faq_workbench_surface_materialization_service.py"
)


def test_final_reconciliation_service_exists_as_current_advisory_boundary() -> None:
    assert FINAL_RECONCILIATION_SERVICE.exists()
    source = FINAL_RECONCILIATION_SERVICE.read_text(encoding="utf-8")

    assert "FinalReconciliation" in source
    assert "PersistFinalReconciliationNodeOutputCommand" in source
    assert "ProcessFinalReconciliationGenerationErrorCommand" in source


def test_final_reconciliation_generator_exists_without_old_surface_materialization() -> (
    None
):
    assert FINAL_RECONCILIATION_GENERATOR.exists()
    assert not OLD_SURFACE_MATERIALIZATION.exists()

    source = FINAL_RECONCILIATION_GENERATOR.read_text(encoding="utf-8")
    assert "FinalReconciliation" in source
    assert "FaqWorkbenchFinalReconciliationGenerator" in source
    assert "surface_materialization" not in source


def test_old_sequential_orchestrator_is_retired_not_runtime_contract() -> None:
    source = OLD_SEQUENTIAL_ORCHESTRATOR.read_text(encoding="utf-8")

    assert "RetiredSequentialWorkbenchOrchestratorError" in source
    assert "_process_sections_against_registry" not in source
    assert "_ensure_parallel_finalization_ready" not in source
