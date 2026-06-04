from __future__ import annotations

from pathlib import Path


def test_production_repository_no_longer_exposes_old_section_work_item_contract() -> (
    None
):
    source = Path("src/infrastructure/db/knowledge_workbench_repository.py").read_text()

    forbidden_tokens = (
        "async def create_section_batch_plan(",
        "async def create_section_work_items(",
        "async def update_section_work_items(",
        "async def get_latest_section_batch_plan(",
        "async def list_section_work_items(",
        "WorkbenchSectionBatchPlan",
        "WorkbenchSectionWorkItem",
        "work_item_id,",
        "based_on_snapshot_id,",
        "findings_node_run_id,",
        "dedup_node_run_id,",
        "registry_application_node_run_id,",
    )

    for token in forbidden_tokens:
        assert token not in source

    assert "async def create_parallel_section_batch_plan(" in source
    assert "SectionBatchQueueItem" in source
    assert "queue_item_id," in source
    assert "observed_registry_snapshot_id," in source
    assert "claim_observations_node_run_id," in source


def test_central_workbench_ports_do_not_export_old_section_work_item_repository_port() -> (
    None
):
    source = Path("src/application/ports/knowledge_workbench.py").read_text()

    assert "KnowledgeWorkbenchSectionBatchPlanningRepositoryPort" not in source
    assert "WorkbenchSectionBatchPlan" not in source
    assert "WorkbenchSectionWorkItem" not in source

    assert "KnowledgeWorkbenchSectionBatchQueueRepositoryPort" in source
    assert "create_parallel_section_batch_plan" in source
    assert "SectionBatchQueueItem" in source


def test_retired_section_batch_planning_service_is_not_wired_into_runtime_composition() -> (
    None
):
    active_roots = (
        Path("src/interfaces/composition"),
        Path("src/infrastructure/queue/handlers"),
        Path("src/application/workbench"),
        Path("src/application/workbench_commands"),
    )

    forbidden_import = "faq_workbench_section_batch_planning_service"

    for root in active_roots:
        for path in root.rglob("*.py"):
            source = path.read_text()
            assert forbidden_import not in source, str(path)
