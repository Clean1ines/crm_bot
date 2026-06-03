from __future__ import annotations

from pathlib import Path


SERVICE = Path(
    "src/application/services/faq_workbench_parallel_processing_coordinator_service.py"
)


def _read(path: Path) -> str:
    assert path.exists(), f"missing expected source file: {path}"
    return path.read_text(encoding="utf-8")


def test_parallel_coordinator_exists_as_dedicated_execution_boundary() -> None:
    source = _read(SERVICE)

    assert "class FaqWorkbenchParallelProcessingCoordinatorService" in source
    assert "RunParallelWorkbenchProcessingCommand" in source
    assert "ProcessParallelSectionWorkItemCommand" in source
    assert "ProcessParallelRegistryApplicationWorkItemCommand" in source
    assert "SectionWorkItemProcessorPort" in source
    assert "RegistryApplicationWorkItemProcessorPort" in source


def test_parallel_coordinator_uses_parallel_section_wave_and_single_registry_writer() -> (
    None
):
    source = _read(SERVICE)

    assert "asyncio.gather" in source
    assert "_run_section_worker_wave" in source
    assert "_drain_registry_writer" in source
    assert "section_worker_count" in source

    section_wave_index = source.index("async def _run_section_worker_wave(")
    registry_drain_index = source.index("async def _drain_registry_writer(")
    assert section_wave_index < registry_drain_index


def test_parallel_coordinator_does_not_detour_into_resume_cancel_stop() -> None:
    source = _read(SERVICE)

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


def test_parallel_coordinator_does_not_restore_legacy_compiler() -> None:
    source = _read(SERVICE)

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


def test_parallel_coordinator_does_not_mutate_registry_directly() -> None:
    source = _read(SERVICE)

    forbidden = (
        "RegistryUpdateAppliedBy",
        "RegistryUpdateApplication(",
        "create_registry_update_applications",
        "upsert_question_registry_entries",
        "apply_findings_to_registry",
    )
    for marker in forbidden:
        assert marker not in source
