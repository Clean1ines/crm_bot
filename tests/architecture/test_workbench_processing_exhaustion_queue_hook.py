from __future__ import annotations

from pathlib import Path


def test_worker_loop_marks_exhausted_workbench_document_jobs() -> None:
    source = Path("src/infrastructure/queue/worker_loop.py").read_text(encoding="utf-8")

    assert "TASK_PROCESS_WORKBENCH_DOCUMENT" in source
    assert "mark_process_workbench_document_exhausted" in source
    assert "mark_process_knowledge_upload_exhausted" not in source
    assert "TASK_PROCESS_KNOWLEDGE_UPLOAD" not in source
    assert "error=decision.error" in source


def test_workbench_document_handler_persists_exhaustion_transition() -> None:
    source = Path("src/infrastructure/queue/handlers/workbench_document.py").read_text(
        encoding="utf-8"
    )

    assert "decide_processing_exhaustion_transition" in source
    assert "persist_processing_exhaustion_transition" in source
    assert "mark_process_workbench_document_exhausted" in source


def test_workbench_repository_has_first_class_exhaustion_persistence() -> None:
    source = Path("src/infrastructure/db/knowledge_workbench_repository.py").read_text(
        encoding="utf-8"
    )

    assert "persist_processing_exhaustion_transition" in source
    assert "knowledge_workbench_documents" in source
    assert "knowledge_workbench_processing_runs" in source
    assert "last_error_kind" in source
    assert "resume_policy" in source
