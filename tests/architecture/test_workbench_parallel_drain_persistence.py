from __future__ import annotations

from pathlib import Path


DOMAIN = Path("src/domain/project_plane/knowledge_workbench/parallel_drain_policy.py")
REPO = Path("src/infrastructure/db/knowledge_workbench_repository.py")


def _read(path: Path) -> str:
    assert path.exists(), f"missing expected source file: {path}"
    return path.read_text(encoding="utf-8")


def test_parallel_drain_policy_exists_before_finalization_wiring() -> None:
    source = _read(DOMAIN)

    assert "ParallelDrainWorkCounts" in source
    assert "ParallelFinalizationDecision" in source
    assert "decide_parallel_finalization" in source
    assert "ensure_parallel_processing_can_finalize" in source
    assert "CAN_FINALIZE" in source
    assert "KEEP_DRAINING" in source
    assert "BLOCKED_BY_LEASES" in source
    assert "WAITING_FOR_FRESH_REGISTRY" in source
    assert "FAILED" in source


def test_workbench_repository_can_count_parallel_drain_state_from_persistent_queues() -> (
    None
):
    source = _read(REPO)

    assert "async def get_parallel_processing_drain_counts(" in source
    assert "ParallelDrainWorkCounts(" in source
    assert "knowledge_workbench_section_batch_queue_items" in source
    assert "knowledge_workbench_fact_registry_application_queue" in source

    expected_statuses = (
        "ready",
        "leased",
        "claim_observations_persisted",
        "registry_application_queued",
        "waiting_for_fresh_registry",
        "registry_application_applied",
        "failed",
        "applied",
        "superseded",
    )
    for status in expected_statuses:
        assert status in source


def test_parallel_drain_persistence_does_not_detour_into_resume_cancel_stop_or_legacy() -> (
    None
):
    combined = _read(DOMAIN) + _read(REPO)

    forbidden = (
        "resume_workbench",
        "cancel_workbench",
        "stop_workbench",
        "ensure_document_can_be_resumed",
        "decide_processing_cancel_transition",
        "decide_processing_resume_or_recovery_transition",
        "knowledge_surface_compiler",
        "knowledge_surface_parallel_graph_compiler",
        "process_knowledge_upload",
        "AnswerCandidate",
        "CandidateCluster",
        "KnowledgeSurfaceCompilerPort",
    )
    for marker in forbidden:
        assert marker not in combined
