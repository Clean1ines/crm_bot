import inspect

from src.infrastructure.db.knowledge_workbench_repository import (
    KnowledgeWorkbenchRepository,
)


REQUIRED_WORKER_RUNTIME_METHODS = (
    "get_fact_registry_for_run",
    "get_latest_registry_snapshot",
    "get_document_section",
    "lease_next_ready_section_work_item",
    "update_section_batch_queue_item",
    "create_processing_node_run",
    "create_processing_node_artifact",
    "list_claim_observation_parsed_artifacts",
    "sync_processing_run_llm_usage_totals",
    "persist_claim_observations_generation_error_lifecycle",
)


REQUIRED_UPLOAD_RUNTIME_METHODS = (
    "create_document",
    "create_document_sections",
    "create_processing_run",
    "create_fact_registry",
    "create_processing_node_run",
    "create_processing_node_artifact",
    "create_registry_snapshot",
    "create_parallel_section_batch_plan",
)


def test_knowledge_workbench_repository_defines_worker_runtime_methods_concretely() -> (
    None
):
    missing: list[str] = []

    for method_name in REQUIRED_WORKER_RUNTIME_METHODS:
        value = KnowledgeWorkbenchRepository.__dict__.get(method_name)
        if value is None or not inspect.iscoroutinefunction(value):
            missing.append(method_name)

    assert not missing, "Concrete repository methods missing: " + ", ".join(missing)


def test_knowledge_workbench_repository_defines_upload_runtime_methods_concretely() -> (
    None
):
    missing: list[str] = []

    for method_name in REQUIRED_UPLOAD_RUNTIME_METHODS:
        value = KnowledgeWorkbenchRepository.__dict__.get(method_name)
        if value is None or not inspect.iscoroutinefunction(value):
            missing.append(method_name)

    assert not missing, "Concrete repository methods missing: " + ", ".join(missing)
