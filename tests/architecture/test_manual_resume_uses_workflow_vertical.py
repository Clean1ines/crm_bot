from __future__ import annotations

from pathlib import Path


def test_http_manual_resume_uses_current_workflow_vertical_not_legacy_queue() -> None:
    source = Path("src/interfaces/http/knowledge.py").read_text(encoding="utf-8")

    required = (
        "make_knowledge_extraction_workflow_resume(",
        "RunKnowledgeExtractionWorkflowResumeCommand(",
        "KnowledgeExtractionWorkflowResumeNotFoundError",
    )
    missing = [marker for marker in required if marker not in source]
    assert missing == []

    forbidden = (
        "get_queue_repo",
        "queue_repo=Depends(",
        "resume_workbench_document",
        "WorkbenchManualResumeService",
        "WorkbenchResumeParallelQueueAdapter",
        "TASK_PROCESS_WORKBENCH_PARALLEL_PROCESSING",
        "faq_workbench_resume",
    )
    violations = [marker for marker in forbidden if marker in source]
    assert violations == []


def test_legacy_manual_resume_composition_is_not_restored() -> None:
    path = Path("src/interfaces/composition/faq_workbench_resume.py")
    if not path.exists():
        return

    source = path.read_text(encoding="utf-8")
    forbidden = (
        "QueueRepository",
        "WorkbenchResumeParallelQueueAdapter",
        "TASK_PROCESS_WORKBENCH_PARALLEL_PROCESSING",
        "WorkbenchManualResumeService",
        "src.application.workbench_commands.manual_resume",
    )
    violations = [marker for marker in forbidden if marker in source]
    assert violations == []


def test_new_manual_resume_composition_drains_workflow_runtime_commands() -> None:
    source = Path(
        "src/interfaces/composition/knowledge_extraction_workflow_resume.py"
    ).read_text(encoding="utf-8")

    required = (
        "DrainKnowledgeExtractionWorkflowCommands",
        "knowledge_extraction_workflow_runs",
        "workflow_run_id",
        "source_document_ref",
        "PostgresWorkflowRuntimeUnitOfWork",
    )
    missing = [marker for marker in required if marker not in source]
    assert missing == []
