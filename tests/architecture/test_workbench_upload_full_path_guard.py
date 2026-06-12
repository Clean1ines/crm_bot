from __future__ import annotations

from pathlib import Path


def test_current_http_upload_uses_source_ingestion_workflow_not_legacy_queue_upload() -> (
    None
):
    source = Path("src/interfaces/http/knowledge.py").read_text(encoding="utf-8")

    assert "make_knowledge_extraction_workflow_after_upload(" in source
    assert "RunSourceIngestionFirstPhaseCommand(" in source
    assert "RunKnowledgeExtractionWorkflowAfterUploadCommand(" in source

    forbidden = (
        "upload_faq_workbench_knowledge_file",
        "FaqWorkbenchUploadService",
        "WorkbenchQueueAdapter",
        "WorkbenchParallelQueueAdapter",
        "TASK_PROCESS_WORKBENCH_DOCUMENT",
        "TASK_PROCESS_WORKBENCH_PARALLEL_PROCESSING",
        "process_workbench_document",
        "process_workbench_parallel_processing",
        "get_queue_repo",
        "queue_repo=Depends(",
    )
    violations = [marker for marker in forbidden if marker in source]
    assert violations == []


def test_telegram_upload_uses_current_source_ingestion_workflow_vertical() -> None:
    source = Path(
        "src/interfaces/telegram/platform_admin/knowledge_upload.py"
    ).read_text(encoding="utf-8")

    required = (
        "make_knowledge_extraction_workflow_after_upload(",
        "RunSourceIngestionFirstPhaseCommand(",
        "RunKnowledgeExtractionWorkflowAfterUploadCommand(",
        "SourceIngestionActor(",
    )
    missing = [marker for marker in required if marker not in source]
    assert missing == []

    forbidden = (
        "upload_faq_workbench_knowledge_file",
        "src.interfaces.composition.faq_workbench_upload",
        "QueueRepository(",
        "WorkbenchQueueAdapter",
        "WorkbenchParallelQueueAdapter",
        "TASK_PROCESS_WORKBENCH_DOCUMENT",
        "TASK_PROCESS_WORKBENCH_PARALLEL_PROCESSING",
        "process_workbench_document",
        "process_workbench_parallel_processing",
    )
    violations = [marker for marker in forbidden if marker in source]
    assert violations == []


def test_generic_queue_worker_does_not_import_legacy_llm_package_side_effects() -> None:
    source = Path("src/infrastructure/queue/worker_loop.py").read_text(encoding="utf-8")

    forbidden = (
        "src.infrastructure.llm",
        "configured_groq_api_keys",
        "faq_workbench",
        "knowledge_workbench",
        "handlers.rag_eval",
        "run_full_rag_eval",
        "workbench_runtime_retrieval_repository",
    )
    violations = [marker for marker in forbidden if marker in source]
    assert violations == []


def test_legacy_workbench_queue_upload_paths_do_not_exist() -> None:
    deleted_paths = (
        "src/interfaces/composition/faq_workbench_upload.py",
        "src/interfaces/composition/faq_workbench_resume.py",
        "src/infrastructure/queue/workbench_queue.py",
        "src/infrastructure/queue/workbench_parallel_queue.py",
        "src/infrastructure/queue/handlers/workbench_document.py",
        "src/infrastructure/queue/handlers/workbench_parallel_processing.py",
        "src/infrastructure/queue/handlers/workbench_parallel_processing_terminal.py",
    )

    leftovers = [path for path in deleted_paths if Path(path).exists()]
    assert leftovers == []
