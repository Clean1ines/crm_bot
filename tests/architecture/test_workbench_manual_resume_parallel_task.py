from __future__ import annotations

from pathlib import Path


def test_manual_resume_composition_uses_resume_specific_parallel_queue_adapter() -> (
    None
):
    source = Path("src/interfaces/composition/faq_workbench_resume.py").read_text()

    assert "WorkbenchResumeParallelQueueAdapter" in source
    assert "TASK_PROCESS_WORKBENCH_PARALLEL_PROCESSING" in source
    assert "task_type=TASK_PROCESS_WORKBENCH_PARALLEL_PROCESSING" in source
    assert '"section_worker_count": 4' in source

    assert "WorkbenchQueueAdapter" not in source
    assert "WorkbenchParallelQueueAdapter" not in source
    assert "src.infrastructure.queue.workbench_queue" not in source
    assert "src.infrastructure.queue.workbench_parallel_queue" not in source


def test_parallel_queue_adapter_keeps_manual_resume_compatibility_method() -> None:
    source = Path("src/infrastructure/queue/workbench_parallel_queue.py").read_text()
    handler_source = Path(
        "src/infrastructure/queue/handlers/workbench_parallel_processing.py"
    ).read_text()

    assert "class WorkbenchParallelQueueAdapter" in source
    assert "async def enqueue_process_workbench_document(" in source
    assert "enqueue_process_workbench_parallel_processing" in source
    assert "PARALLEL_WORKBENCH_PROCESSING_TASK_TYPE" in source
    assert "TASK_PROCESS_WORKBENCH_DOCUMENT" not in source
    assert "TASK_PROCESS_WORKBENCH_PARALLEL_PROCESSING" not in source

    assert (
        'PARALLEL_WORKBENCH_PROCESSING_TASK_TYPE = "process_workbench_parallel_processing"'
        in handler_source
    )


def test_manual_resume_service_remains_queue_type_agnostic() -> None:
    source = Path("src/application/workbench_commands/manual_resume.py").read_text()

    assert "src.infrastructure.queue.workbench_queue" not in source
    assert "src.infrastructure.queue.workbench_parallel_queue" not in source
    assert "WorkbenchQueueAdapter" not in source
    assert "WorkbenchParallelQueueAdapter" not in source
