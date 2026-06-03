from __future__ import annotations

from pathlib import Path


DOMAIN = Path("src/domain/project_plane/knowledge_workbench/section_batch_queue.py")
GRAPH_CONTRACT = Path("src/application/workbench/processing_graph_contract.py")
ORCH = Path(
    "src/application/services/faq_workbench_document_processing_orchestrator.py"
)
RESUME_COMPOSITION = Path("src/interfaces/composition/faq_workbench_resume.py")
CANCEL_COMPOSITION = Path("src/interfaces/composition/faq_workbench_cancel.py")


def _read(path: Path) -> str:
    assert path.exists(), f"missing expected source file: {path}"
    return path.read_text(encoding="utf-8")


def test_parallel_section_batch_domain_exists_for_process_parallel_section_batch_node() -> (
    None
):
    domain_source = _read(DOMAIN)
    graph_source = _read(GRAPH_CONTRACT)

    assert "class SectionBatchQueueItem" in domain_source
    assert "class ParallelSectionBatchPlan" in domain_source
    assert "plan_parallel_section_batch" in domain_source
    assert "observed_registry_snapshot_id" in domain_source
    assert "observed_registry_snapshot_sequence" in domain_source
    assert "ProcessingNodeName.PROCESS_PARALLEL_SECTION_BATCH" in graph_source


def test_parallel_section_batch_domain_does_not_import_resume_stop_cancel_lifecycle() -> (
    None
):
    domain_source = _read(DOMAIN)

    forbidden = (
        "ResumePolicy",
        "decide_processing_resume_or_recovery_transition",
        "decide_processing_cancel_transition",
        "is_processing_cancelled_for_workbench",
        "ensure_document_can_be_resumed",
        "ensure_document_can_be_processed",
        "cancel",
        "resume",
    )
    for marker in forbidden:
        assert marker not in domain_source


def test_resume_and_cancel_are_not_rewired_to_new_parallel_queue_yet() -> None:
    resume_source = _read(RESUME_COMPOSITION)
    cancel_source = _read(CANCEL_COMPOSITION)
    orchestrator_source = _read(ORCH)

    forbidden = (
        "SectionBatchQueueItem",
        "ParallelSectionBatchPlan",
        "plan_parallel_section_batch",
        "section_batch_queue",
    )
    for source_name, source in {
        "resume": resume_source,
        "cancel": cancel_source,
        "orchestrator": orchestrator_source,
    }.items():
        for marker in forbidden:
            assert marker not in source, f"{marker} leaked into {source_name}"


def test_section_batch_planning_is_not_a_second_registry_mutator() -> None:
    domain_source = _read(DOMAIN)

    forbidden = (
        "RegistryUpdateApplication(",
        "RegistryUpdateAppliedBy",
        "apply_findings_to_registry",
        "upsert_question_registry_entries",
        "create_registry_update_applications",
        "generate_registry_updates",
    )
    for marker in forbidden:
        assert marker not in domain_source
