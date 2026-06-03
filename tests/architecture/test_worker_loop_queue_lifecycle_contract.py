from __future__ import annotations

from pathlib import Path


WORKER = Path("src/infrastructure/queue/worker_loop.py")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_worker_loop_completes_job_on_normal_dispatch_return() -> None:
    source = _read(WORKER)
    dispatch_block = source.split("await dispatcher.dispatch", 1)[1].split(
        "except Exception as exc:",
        1,
    )[0]

    assert "else:" in dispatch_block
    assert "await queue_repo.complete_job(job_id, success=True)" in dispatch_block
    assert "Job completed successfully" in dispatch_block


def test_worker_loop_keeps_transient_and_permanent_paths_explicit() -> None:
    source = _read(WORKER)

    assert "except PermanentJobError as exc:" in source
    assert "await queue_repo.complete_job(job_id, success=False, error=str(exc))" in source
    assert "except TransientJobError as exc:" in source
    assert "await queue_repo.fail_job(" in source
    assert "build_retry_decision(" in source


def test_worker_loop_does_not_break_after_single_processed_job() -> None:
    source = _read(WORKER)
    dispatch_block = source.split("await dispatcher.dispatch", 1)[1].split(
        "except Exception as exc:",
        1,
    )[0]

    assert "Worker loop cancelled" not in source
    assert "\n            break\n" not in dispatch_block
