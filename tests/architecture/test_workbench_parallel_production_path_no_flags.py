from __future__ import annotations

from pathlib import Path


HANDLER = Path("src/infrastructure/queue/handlers/workbench_parallel_processing.py")
QUEUE = Path("src/infrastructure/queue/workbench_parallel_queue.py")
JOB_TYPES = Path("src/infrastructure/queue/job_types.py")
DISPATCHER = Path("src/infrastructure/queue/job_dispatcher.py")
UPLOAD = Path("src/interfaces/composition/faq_workbench_upload.py")


def _read(path: Path) -> str:
    assert path.exists(), f"missing expected source file: {path}"
    return path.read_text(encoding="utf-8")


def test_parallel_processing_has_no_env_gate_anywhere() -> None:
    combined = ""
    for path in (HANDLER, QUEUE, JOB_TYPES, DISPATCHER, UPLOAD):
        combined += path.read_text(encoding="utf-8")

    forbidden = (
        "FAQ_WORKBENCH_PARALLEL_PROCESSING_ENABLED",
        "parallel_workbench_processing_enabled",
        "ParallelWorkbenchDispatchGate",
        "dispatch_parallel_workbench_processing_if_enabled",
        "BLOCKED_BY_GATE",
    )
    for marker in forbidden:
        assert marker not in combined


def test_parallel_processing_is_known_dispatch_task_type() -> None:
    job_types = _read(JOB_TYPES)
    dispatcher = _read(DISPATCHER)

    assert "TASK_PROCESS_WORKBENCH_PARALLEL_PROCESSING" in job_types
    assert "TASK_PROCESS_WORKBENCH_PARALLEL_PROCESSING," in job_types
    assert "TASK_PROCESS_WORKBENCH_PARALLEL_PROCESSING" in dispatcher
    assert "handle_workbench_parallel_processing_job_from_connection" in dispatcher


def test_upload_uses_parallel_queue_adapter_as_production_upload_path() -> None:
    upload = _read(UPLOAD)

    assert "WorkbenchParallelQueueAdapter" in upload
    assert "WorkbenchQueueAdapter" not in upload
    assert "WorkbenchParallelQueueAdapter(connection=queue_repo)" in upload


def test_parallel_queue_adapter_is_upload_service_compatible() -> None:
    queue = _read(QUEUE)

    assert "async def enqueue_process_workbench_document(" in queue
    assert "enqueue_process_workbench_parallel_processing(" in queue
    assert "TASK_PROCESS_WORKBENCH_DOCUMENT" not in queue


def test_parallel_production_path_does_not_restore_legacy_compiler() -> None:
    combined = _read(HANDLER) + _read(QUEUE) + _read(DISPATCHER) + _read(UPLOAD)

    forbidden = (
        "knowledge_surface_compiler",
        "knowledge_surface_parallel_graph_compiler",
        "process_knowledge_upload",
        "AnswerCandidate",
        "CandidateCluster",
        "KnowledgeSurfaceCompilerPort",
    )
    for marker in forbidden:
        assert marker not in combined
