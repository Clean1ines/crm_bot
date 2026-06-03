from __future__ import annotations

from pathlib import Path


HANDLER = Path("src/infrastructure/queue/handlers/workbench_parallel_processing.py")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_parallel_handler_inspects_coordinator_result_before_returning_to_dispatcher() -> None:
    source = _read(HANDLER)
    handler_source = source.split(
        "async def handle_workbench_parallel_processing_job",
        1,
    )[1].split(
        "class DefaultClaimObservationsRunner",
        1,
    )[0]

    assert "result = await coordinator.run_parallel_processing" in handler_source
    assert "_ensure_parallel_processing_terminal_result(result)" in handler_source
    assert "return result" in handler_source


def test_parallel_handler_converts_non_terminal_result_to_queue_retry_or_failure() -> None:
    source = _read(HANDLER)
    guard_source = source.split(
        "def _ensure_parallel_processing_terminal_result",
        1,
    )[1].split(
        "def _required_text",
        1,
    )[0]

    assert "completed_without_work_left" in guard_source
    assert "TransientJobError" in guard_source
    assert "PermanentJobError" in guard_source
    assert "blocked_by_leases" in guard_source
    assert "keep_draining" in guard_source
    assert "wait_for_snapshot" in guard_source
    assert "failed" in guard_source
