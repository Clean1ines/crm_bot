from __future__ import annotations

from pathlib import Path


def test_workbench_observability_auto_recovery_uses_parallel_task_type() -> None:
    source = Path(
        "src/infrastructure/db/workbench_observability_repository.py"
    ).read_text()

    auto_recovery_start = source.index("auto_recovery.auto_resume_scheduled_at")
    auto_recovery_source = source[auto_recovery_start:]

    assert "process_workbench_parallel_processing" in auto_recovery_source
    assert (
        "q.task_type = 'process_workbench_parallel_processing'" in auto_recovery_source
    )
    assert "q.payload::jsonb ->> 'project_id'" in auto_recovery_source
    assert "q.payload::jsonb ->> 'document_id'" in auto_recovery_source
    assert "q.next_attempt_at IS NOT NULL" in auto_recovery_source

    assert "q.task_type = 'process_workbench_document'" not in auto_recovery_source


def test_retired_process_workbench_document_is_not_observability_auto_recovery_source() -> (
    None
):
    source = Path(
        "src/infrastructure/db/workbench_observability_repository.py"
    ).read_text()

    assert "process_workbench_document" not in source
    assert "process_workbench_parallel_processing" in source
