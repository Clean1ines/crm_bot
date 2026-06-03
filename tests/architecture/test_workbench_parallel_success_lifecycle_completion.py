from __future__ import annotations

from pathlib import Path


COORDINATOR = Path(
    "src/application/services/faq_workbench_parallel_processing_coordinator_service.py"
)
PORT = Path("src/application/ports/knowledge_workbench.py")
REPOSITORY = Path("src/infrastructure/db/knowledge_workbench_repository.py")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_parallel_coordinator_has_success_lifecycle_completion_port() -> None:
    source = _read(COORDINATOR)

    assert "ParallelProcessingLifecycleCompletionPort" in source
    assert "mark_parallel_processing_completed" in source
    assert "_mark_success_lifecycle_if_terminal" in source
    assert "_cycle_is_terminal_success" in source


def test_parallel_success_lifecycle_completion_is_declared_in_repository_port() -> None:
    source = _read(PORT)

    assert "async def mark_parallel_processing_completed" in source


def test_parallel_success_lifecycle_completion_updates_document_and_processing_run() -> None:
    source = _read(REPOSITORY)

    assert "async def mark_parallel_processing_completed" in source
    assert "UPDATE knowledge_workbench_documents" in source
    assert "UPDATE knowledge_workbench_processing_runs" in source
    assert "status = 'processed'" in source
    assert "status = 'completed'" in source
    assert "resume_policy = 'forbidden'" in source
    assert "completed_at = COALESCE(completed_at, now())" in source


def test_parallel_success_lifecycle_completion_is_not_triggered_on_blocking_outcomes() -> None:
    source = _read(COORDINATOR)
    terminal_function = source.split("def _cycle_is_terminal_success", 1)[1].split(
        "def _section_wave_is_drained",
        1,
    )[0]

    for marker in (
        "blocked_by_sections",
        "blocked_by_leases",
        "waiting_for_fresh_registry",
        "wait_for_snapshot",
        "keep_draining",
        "failed",
    ):
        assert marker in terminal_function
