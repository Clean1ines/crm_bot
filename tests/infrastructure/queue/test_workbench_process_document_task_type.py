from __future__ import annotations

from src.infrastructure.queue.job_types import TASK_PROCESS_WORKBENCH_DOCUMENT


def test_process_workbench_document_task_type_value() -> None:
    assert TASK_PROCESS_WORKBENCH_DOCUMENT == "process_workbench_document"
