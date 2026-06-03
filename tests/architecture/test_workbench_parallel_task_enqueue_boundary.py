from __future__ import annotations

from pathlib import Path


QUEUE = Path("src/infrastructure/queue/workbench_parallel_queue.py")
HANDLER = Path("src/infrastructure/queue/handlers/workbench_parallel_processing.py")
JOB_TYPES = Path("src/infrastructure/queue/job_types.py")
JOB_DISPATCHER = Path("src/infrastructure/queue/job_dispatcher.py")
WORKER_LOOP = Path("src/infrastructure/queue/worker_loop.py")
UPLOAD_COMPOSITION = Path("src/interfaces/composition/faq_workbench_upload.py")
RESUME_COMPOSITION = Path("src/interfaces/composition/faq_workbench_resume.py")


def _read(path: Path) -> str:
    assert path.exists(), f"missing expected source file: {path}"
    return path.read_text(encoding="utf-8")


def test_parallel_queue_enqueue_boundary_exists() -> None:
    source = _read(QUEUE)

    assert "WorkbenchParallelQueueAdapter" in source
    assert "EnqueueWorkbenchParallelProcessingCommand" in source
    assert "enqueue_process_workbench_parallel_processing" in source
    assert "process_workbench_parallel_processing" in source
    assert "INSERT INTO execution_queue" in source


def test_parallel_enqueue_reuses_parallel_handler_payload_contract() -> None:
    source = _read(QUEUE)
    handler_source = _read(HANDLER)

    assert "WorkbenchParallelProcessingJobPayloadDto" in source
    assert "WorkbenchParallelProcessingJobPayloadDto" in handler_source
    assert "PARALLEL_WORKBENCH_PROCESSING_TASK_TYPE" in source
    assert "PARALLEL_WORKBENCH_PROCESSING_TASK_TYPE" in handler_source


def test_parallel_task_is_registered_in_dispatcher_now() -> None:
    job_types_source = _read(JOB_TYPES)
    dispatcher_source = _read(JOB_DISPATCHER)
    worker_loop_source = _read(WORKER_LOOP)

    assert (
        "TASK_PROCESS_WORKBENCH_PARALLEL_PROCESSING = "
        '"process_workbench_parallel_processing"' in job_types_source
    )
    assert "TASK_PROCESS_WORKBENCH_PARALLEL_PROCESSING" in job_types_source
    assert "TASK_PROCESS_WORKBENCH_PARALLEL_PROCESSING" in dispatcher_source
    assert (
        "handle_workbench_parallel_processing_job_from_connection" in dispatcher_source
    )
    assert (
        "if task_type == TASK_PROCESS_WORKBENCH_PARALLEL_PROCESSING:"
        in dispatcher_source
    )

    # The worker loop must remain generic: it claims jobs and delegates to JobDispatcher.
    # It should not instantiate the parallel queue adapter directly.
    assert "WorkbenchParallelQueueAdapter" not in worker_loop_source


def test_parallel_enqueue_is_not_called_from_upload_or_resume_yet() -> None:
    upload_source = _read(UPLOAD_COMPOSITION)
    resume_source = _read(RESUME_COMPOSITION)

    assert "enqueue_process_workbench_parallel_processing" not in upload_source
    assert "enqueue_process_workbench_parallel_processing" not in resume_source
    assert "process_workbench_parallel_processing" not in upload_source
    assert "process_workbench_parallel_processing" not in resume_source


def test_parallel_enqueue_does_not_detour_into_resume_cancel_stop() -> None:
    source = _read(QUEUE)

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


def test_parallel_enqueue_does_not_restore_legacy_compiler() -> None:
    source = _read(QUEUE)

    forbidden = (
        "knowledge_surface_compiler",
        "knowledge_surface_parallel_graph_compiler",
        "process_knowledge_upload",
        "AnswerCandidate",
        "CandidateCluster",
        "KnowledgeSurfaceCompilerPort",
    )
    for marker in forbidden:
        assert marker not in source


def test_parallel_enqueue_does_not_mutate_registry_directly() -> None:
    source = _read(QUEUE)

    forbidden = (
        "RegistryUpdateAppliedBy",
        "RegistryUpdateApplication(",
        "create_registry_update_applications",
        "upsert_question_registry_entries",
        "apply_findings_to_registry",
    )
    for marker in forbidden:
        assert marker not in source
