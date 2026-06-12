from __future__ import annotations

import importlib
from pathlib import Path


QUEUE_ROOTS = (
    "src/infrastructure/queue/job_types.py",
    "src/infrastructure/queue/job_dispatcher.py",
    "src/infrastructure/queue/worker_loop.py",
)


def test_legacy_workbench_document_upload_is_not_a_queue_root_dependency() -> None:
    forbidden = (
        "src.infrastructure.queue.handlers.workbench_document",
        "src.infrastructure.queue.handlers.workbench_parallel_processing",
        "src.infrastructure.queue.handlers.workbench_parallel_processing_terminal",
        "handle_process_workbench_document",
        "handle_workbench_parallel_processing",
        "mark_process_workbench_document_exhausted",
        "TASK_PROCESS_WORKBENCH_DOCUMENT",
        "TASK_PROCESS_WORKBENCH_PARALLEL_PROCESSING",
        "process_workbench_document",
        "process_workbench_parallel_processing",
        "WorkbenchQueueAdapter",
        "WorkbenchParallelQueueAdapter",
        "workbench_runtime_retrieval_repository",
        "handlers.rag_eval",
        "handle_run_full_rag_eval",
        "run_full_rag_eval",
        "TASK_RUN_FULL_RAG_EVAL",
    )

    for path in QUEUE_ROOTS:
        source = Path(path).read_text(encoding="utf-8")
        for marker in forbidden:
            assert marker not in source, f"{path} still contains {marker}"


def test_legacy_workbench_document_upload_files_are_deleted() -> None:
    deleted_paths = (
        "src/infrastructure/queue/handlers/workbench_document.py",
        "src/infrastructure/queue/handlers/workbench_parallel_processing.py",
        "src/infrastructure/queue/handlers/workbench_parallel_processing_terminal.py",
        "src/infrastructure/queue/workbench_queue.py",
        "src/infrastructure/queue/workbench_parallel_queue.py",
        "src/interfaces/composition/faq_workbench_upload.py",
        "src/interfaces/composition/faq_workbench_resume.py",
        "src/application/workbench/upload_service.py",
        "src/application/workbench_commands/manual_resume.py",
    )

    leftovers = [path for path in deleted_paths if Path(path).exists()]
    assert leftovers == []


def test_queue_roots_import_without_legacy_workbench_document_upload() -> None:
    for module in (
        "src.infrastructure.queue.job_types",
        "src.infrastructure.queue.job_dispatcher",
        "src.infrastructure.queue.worker_loop",
    ):
        importlib.import_module(module)
