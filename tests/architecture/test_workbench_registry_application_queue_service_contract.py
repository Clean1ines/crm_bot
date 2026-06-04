from pathlib import Path


SERVICE = Path(
    "src/application/services/faq_workbench_registry_application_queue_service.py"
)
WORKER = Path(
    "src/application/services/faq_workbench_registry_application_work_item_processor_service.py"
)


def test_old_registry_application_queue_service_is_retired_guard() -> None:
    source = SERVICE.read_text(encoding="utf-8")

    assert "RetiredRegistryApplicationQueueServiceError" in source
    assert "FaqWorkbenchRegistryApplicationQueueService is retired" in source
    assert "FaqWorkbenchRegistryApplicationWorkItemProcessorService" in source
    assert "Prompt C fact_registry artifacts" in source

    forbidden = (
        "ApplyRegistryFindingsCommand",
        "apply_findings_to_registry",
        "QuestionRegistryEntry",
        "RegistryUpdateApplication",
        "RegistryUpdateProposal",
        "upsert_question_registry_entries",
        "create_registry_update_applications",
    )

    for token in forbidden:
        assert token not in source


def test_registry_application_worker_is_the_queue_application_runtime() -> None:
    source = WORKER.read_text(encoding="utf-8")

    assert "FaqWorkbenchRegistryApplicationWorkItemProcessorService" in source
    assert "apply_fact_registry_snapshot" in source
    assert "get_processing_node_artifact_by_node_run_id_and_type" in source
    assert "ProcessingNodeArtifactType.PARSED_LLM_OUTPUT" in source
