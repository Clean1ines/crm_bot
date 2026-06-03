from pathlib import Path


HANDLER = Path("src/infrastructure/queue/handlers/workbench_document.py")


def test_legacy_workbench_document_handler_does_not_wire_groq_or_orchestrator() -> None:
    source = HANDLER.read_text(encoding="utf-8")

    assert "handle_process_workbench_document" in source
    assert "PermanentJobError" in source

    forbidden = (
        "GroqLlmJsonInvocationAdapter",
        "FaqWorkbenchDocumentProcessingOrchestrator",
        "make_workbench_claim_observations_generator",
        "make_workbench_registry_merge_generator",
        "make_workbench_final_reconciliation_generator",
        "FaqWorkbenchFinalReconciliationGenerator",
        "FaqWorkbenchClaimObservationsGenerator",
        "FaqWorkbenchRegistryMergeGenerator",
        "process_existing_document_sections",
    )

    for token in forbidden:
        assert token not in source
