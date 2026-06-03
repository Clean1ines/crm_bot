from __future__ import annotations

from pathlib import Path


REPO = Path("src/infrastructure/db/knowledge_workbench_repository.py")
PROCESSOR_SERVICE = Path(
    "src/application/services/faq_workbench_section_work_item_processor_service.py"
)


def _read(path: Path) -> str:
    assert path.exists(), f"missing expected source file: {path}"
    return path.read_text(encoding="utf-8")


def test_workbench_repository_exposes_processor_db_methods() -> None:
    source = _read(REPO)

    assert "async def get_document_section(" in source
    assert "async def update_section_batch_queue_item(" in source
    assert "async def create_registry_application_queue_item(" in source

    assert "FROM knowledge_workbench_document_sections" in source
    assert "UPDATE knowledge_workbench_section_batch_queue_items" in source
    assert "INSERT INTO knowledge_workbench_registry_application_queue" in source


def test_processor_db_persistence_uses_latest_snapshot_and_queue_tables() -> None:
    repo_source = _read(REPO)
    processor_source = _read(PROCESSOR_SERVICE)

    assert "get_latest_registry_snapshot" in processor_source
    assert "list_question_registry_entries" in processor_source
    assert "update_section_batch_queue_item" in processor_source
    assert "create_registry_application_queue_item" in processor_source

    assert "observed_registry_snapshot_id" in repo_source
    assert "observed_registry_snapshot_sequence" in repo_source
    assert "claim_observations_node_run_id" in repo_source
    assert "registry_application_queue_item_id" in repo_source
    assert "claim_input_refs" in repo_source


def test_processor_db_persistence_does_not_detour_into_resume_cancel_stop() -> None:
    combined = _read(REPO) + _read(PROCESSOR_SERVICE)

    forbidden = (
        "resume_workbench",
        "cancel_workbench",
        "stop_workbench",
        "ensure_document_can_be_resumed",
        "decide_processing_cancel_transition",
        "decide_processing_resume_or_recovery_transition",
    )
    for marker in forbidden:
        assert marker not in combined


def test_processor_db_persistence_does_not_restore_legacy_compiler() -> None:
    combined = _read(REPO) + _read(PROCESSOR_SERVICE)

    forbidden = (
        "knowledge_surface_" + "compiler",
        "knowledge_surface_" + "parallel_graph_compiler",
        "process_knowledge_upload",
        "AnswerCandidate",
        "CandidateCluster",
        "KnowledgeSurfaceCompilerPort",
    )
    for marker in forbidden:
        assert marker not in combined
