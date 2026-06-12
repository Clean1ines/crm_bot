from __future__ import annotations

from pathlib import Path


def test_current_vertical_source_roots_are_present() -> None:
    required = (
        "src/contexts/llm_runtime",
        "src/contexts/execution_runtime",
        "src/contexts/workflow_runtime",
        "src/contexts/knowledge_workbench/source_management",
        "src/contexts/knowledge_workbench/application/sagas",
        "src/contexts/knowledge_workbench/extraction",
        "src/interfaces/http/knowledge.py",
        "src/interfaces/telegram/platform_admin/knowledge_upload.py",
    )

    missing = [path for path in required if not Path(path).exists()]
    assert missing == []


def test_rag_eval_is_parked_not_connected_to_old_execution_queue() -> None:
    rag_eval_source = Path("src/interfaces/http/rag_eval.py").read_text(
        encoding="utf-8"
    )
    job_types_source = Path("src/infrastructure/queue/job_types.py").read_text(
        encoding="utf-8"
    )
    dispatcher_source = Path("src/infrastructure/queue/job_dispatcher.py").read_text(
        encoding="utf-8"
    )

    assert "APIRouter" in rag_eval_source
    assert "HTTP_410_GONE" in rag_eval_source

    forbidden = (
        "TASK_RUN_FULL_RAG_EVAL",
        "TASK_PROCESS_WORKBENCH_DOCUMENT",
        "TASK_PROCESS_WORKBENCH_PARALLEL_PROCESSING",
        "handle_run_full_rag_eval",
        "handle_process_workbench_document",
        "handle_workbench_parallel_processing",
        "QueueRepository",
        "get_queue_repo",
        "workbench_runtime_retrieval_repository",
        "workbench_rag_eval_edit_repository",
    )

    combined = "\n".join((rag_eval_source, job_types_source, dispatcher_source))
    violations = [marker for marker in forbidden if marker in combined]
    assert violations == []


def test_obsolete_workbench_tests_are_not_in_current_gate() -> None:
    forbidden_patterns = (
        "tests/application/services/test_faq_workbench_*.py",
        "tests/application/workbench/**/*.py",
        "tests/application/workbench_commands/**/*.py",
        "tests/interfaces/composition/test_faq_workbench_parallel_processing_composition.py",
        "tests/infrastructure/queue/test_workbench_prompt_a_*.py",
        "tests/infrastructure/queue/**/*workbench*.py",
        "tests/integration/workbench/test_workbench_upload_to_runtime_e2e_smoke.py",
        "tests/integration/workbench/test_workbench_publish_ready_runtime_projection.py",
        "tests/api/test_rag_eval_full_enqueue_contract.py",
    )

    leftovers: list[str] = []
    for pattern in forbidden_patterns:
        leftovers.extend(str(path) for path in Path(".").glob(pattern))

    assert sorted(leftovers) == []
