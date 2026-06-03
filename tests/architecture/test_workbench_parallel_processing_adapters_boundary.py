from __future__ import annotations

from pathlib import Path


ADAPTERS = Path(
    "src/application/services/faq_workbench_parallel_processing_adapters.py"
)
COORDINATOR = Path(
    "src/application/services/faq_workbench_parallel_processing_coordinator_service.py"
)


def _read(path: Path) -> str:
    assert path.exists(), f"missing expected source file: {path}"
    return path.read_text(encoding="utf-8")


def test_parallel_processing_adapters_exist_as_thin_application_layer() -> None:
    source = _read(ADAPTERS)

    assert "class FaqWorkbenchParallelSectionProcessorAdapter" in source
    assert "class FaqWorkbenchParallelRegistryApplicationProcessorAdapter" in source
    assert "ClaimSectionWorkItemCommand" in source
    assert "ProcessOneSectionWorkItemCommand" in source
    assert "process_next_section_work_item" in source
    assert "process_one_section_work_item" in source
    assert "process_next_registry_application_work_item" in source


def test_section_parallel_adapter_claims_before_processing_one_item() -> None:
    source = _read(ADAPTERS)

    claim_index = source.index("claim_next_ready_section_work_item(")
    process_index = source.index("process_one_section_work_item(")

    assert claim_index < process_index
    assert "queue_item=claim_result.leased_item" in source
    assert "worker_id=command.worker_id" in source
    assert "FaqWorkbenchParallelSectionNoWorkResult" in source
    assert "FaqWorkbenchParallelSectionProcessedResult" in source


def test_parallel_processing_adapters_are_not_queue_handler_wiring_yet() -> None:
    source = _read(ADAPTERS)

    forbidden = (
        "execution_queue",
        "job_dispatcher",
        "worker_loop",
        "WorkbenchQueueAdapter",
        "process_workbench_document",
        "FastAPI",
        "APIRouter",
    )
    for marker in forbidden:
        assert marker not in source


def test_parallel_processing_adapters_do_not_detour_into_resume_cancel_stop() -> None:
    source = _read(ADAPTERS) + _read(COORDINATOR)

    forbidden = (
        "resume_workbench",
        "cancel_workbench",
        "stop_workbench",
        "ensure_document_can_be_resumed",
        "decide_processing_cancel_transition",
        "decide_processing_resume_or_recovery_transition",
    )
    for marker in forbidden:
        assert marker not in source


def test_parallel_processing_adapters_do_not_restore_legacy_compiler() -> None:
    source = _read(ADAPTERS) + _read(COORDINATOR)

    forbidden = (
        "knowledge_surface_" + "compiler",
        "knowledge_surface_" + "parallel_graph_compiler",
        "process_knowledge_upload",
        "AnswerCandidate",
        "CandidateCluster",
        "KnowledgeSurfaceCompilerPort",
    )
    for marker in forbidden:
        assert marker not in source


def test_parallel_processing_adapters_do_not_mutate_registry_directly() -> None:
    source = _read(ADAPTERS)

    forbidden = (
        "RegistryUpdateAppliedBy",
        "RegistryUpdateApplication(",
        "create_registry_update_applications",
        "upsert_question_registry_entries",
        "apply_findings_to_registry",
    )
    for marker in forbidden:
        assert marker not in source
