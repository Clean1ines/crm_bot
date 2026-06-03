from __future__ import annotations

from pathlib import Path


COMPOSITION = Path("src/interfaces/composition/faq_workbench_parallel_processing.py")
QUEUE_HANDLER = Path("src/infrastructure/queue/handlers/workbench_document.py")


def _read(path: Path) -> str:
    assert path.exists(), f"missing expected source file: {path}"
    return path.read_text(encoding="utf-8")


def test_parallel_processing_composition_boundary_exists() -> None:
    source = _read(COMPOSITION)

    assert "FaqWorkbenchParallelProcessingDependencies" in source
    assert "make_faq_workbench_parallel_processing_coordinator" in source
    assert "FaqWorkbenchParallelProcessingCoordinatorService" in source
    assert "FaqWorkbenchParallelSectionProcessorAdapter" in source
    assert "FaqWorkbenchParallelRegistryApplicationProcessorAdapter" in source
    assert "FaqWorkbenchSectionWorkItemLeaseService" in source
    assert "FaqWorkbenchSectionWorkItemProcessorService" in source
    assert "FaqWorkbenchRegistryApplicationWorkItemProcessorService" in source


def test_parallel_processing_composition_keeps_queue_handler_unwired_for_now() -> None:
    composition_source = _read(COMPOSITION)
    handler_source = _read(QUEUE_HANDLER)

    assert "make_faq_workbench_parallel_processing_coordinator" in composition_source
    assert "make_faq_workbench_parallel_processing_coordinator" not in handler_source
    assert "RunParallelWorkbenchProcessingCommand" not in handler_source


def test_parallel_processing_composition_does_not_detour_into_resume_cancel_stop() -> (
    None
):
    source = _read(COMPOSITION)

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


def test_parallel_processing_composition_does_not_restore_legacy_compiler() -> None:
    source = _read(COMPOSITION)

    forbidden = (
        "knowledge_surface_compiler",
        "knowledge_surface_parallel_graph_compiler",
        "process_knowledge_upload",
        "AnswerCandidate",
        "CandidateCluster",
        "KnowledgeSurfaceCompilerPort",
    )
    for marker in forbidden:
        assert marker not in source


def test_parallel_processing_composition_does_not_mutate_registry_directly() -> None:
    source = _read(COMPOSITION)

    forbidden = (
        "RegistryUpdateAppliedBy",
        "RegistryUpdateApplication(",
        "create_registry_update_applications",
        "upsert_question_registry_entries",
        "apply_findings_to_registry",
    )
    for marker in forbidden:
        assert marker not in source
