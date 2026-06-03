from pathlib import Path


SERVICE = Path(
    "src/application/services/faq_workbench_registry_application_work_item_processor_service.py"
)


def test_registry_application_work_item_processor_consumes_fact_registry_artifact() -> None:
    source = SERVICE.read_text(encoding="utf-8")

    assert "FaqWorkbenchRegistryApplicationWorkItemProcessorService" in source
    assert "get_processing_node_artifact_by_node_run_id_and_type" in source
    assert "ProcessingNodeArtifactType.PARSED_LLM_OUTPUT" in source
    assert "apply_fact_registry_snapshot" in source
    assert "ApplyFactRegistrySnapshotCommand" in source

    forbidden = (
        "ApplyRegistryFindingsCommand",
        "apply_findings_to_registry",
        "list_question_registry_entries",
        "list_claim_observations_by_ids",
        "QuestionRegistryEntry",
        "SectionFinding",
        "generate_final_reconciliation",
        "FaqWorkbenchFinalReconciliationGenerator",
    )

    for token in forbidden:
        assert token not in source
