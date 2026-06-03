from __future__ import annotations

import importlib
from pathlib import Path


QUEUE_ROOTS = (
    "src/infrastructure/queue/job_types.py",
    "src/infrastructure/queue/job_dispatcher.py",
    "src/infrastructure/queue/worker_loop.py",
)


def test_legacy_knowledge_upload_handler_is_not_a_queue_root_dependency() -> None:
    forbidden = (
        "src.infrastructure.queue.handlers.knowledge_upload",
        "src.infrastructure.queue.handlers.knowledge_upload_recovery",
        "handle_process_knowledge_upload",
        "mark_process_knowledge_upload_exhausted",
        "TASK_PROCESS_KNOWLEDGE_UPLOAD",
        "process_knowledge_upload",
    )

    for path in QUEUE_ROOTS:
        source = Path(path).read_text(encoding="utf-8")
        for marker in forbidden:
            assert marker not in source, f"{path} still contains {marker}"


def test_legacy_knowledge_upload_handler_files_are_deleted() -> None:
    assert not Path("src/infrastructure/queue/handlers/knowledge_upload.py").exists()
    assert not Path(
        "src/infrastructure/queue/handlers/knowledge_upload_recovery.py"
    ).exists()


def test_queue_roots_import_without_legacy_compiler_chain() -> None:
    for module in (
        "src.infrastructure.queue.job_types",
        "src.infrastructure.queue.job_dispatcher",
        "src.infrastructure.queue.worker_loop",
    ):
        importlib.import_module(module)


def test_workbench_exhaustion_hook_remains_wired() -> None:
    source = Path("src/infrastructure/queue/worker_loop.py").read_text(encoding="utf-8")

    assert "TASK_PROCESS_WORKBENCH_DOCUMENT" in source
    assert "mark_process_workbench_document_exhausted" in source
    assert "mark_process_knowledge_upload_exhausted" not in source
    assert "TASK_PROCESS_KNOWLEDGE_UPLOAD" not in source
