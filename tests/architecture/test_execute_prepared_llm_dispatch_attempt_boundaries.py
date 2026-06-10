from __future__ import annotations

from pathlib import Path


COMPOSITION_PATH = Path(
    "src/interfaces/composition/execute_prepared_llm_dispatch_attempt.py",
)
READ_PORT_PATH = Path(
    "src/contexts/execution_runtime/application/ports/"
    "work_item_attempt_dispatch_read_repository_port.py",
)
READ_REPOSITORY_PATH = Path(
    "src/contexts/execution_runtime/infrastructure/postgres/"
    "postgres_work_item_attempt_dispatch_read_repository.py",
)


def test_execute_prepared_llm_dispatch_attempt_required_markers_exist() -> None:
    source = "\n".join(
        (
            COMPOSITION_PATH.read_text(encoding="utf-8"),
            READ_PORT_PATH.read_text(encoding="utf-8"),
        ),
    )

    required = (
        "ExecutePreparedLlmDispatchAttempt",
        "WorkItemAttemptDispatchReadRepositoryPort",
        "LlmDispatchExecutorPort",
        "RecordWorkItemAttemptOutcome",
        "LlmDispatchExecutionInput",
        "WorkItemAttemptOutcomeStatus",
    )
    for marker in required:
        assert marker in source


def test_execute_prepared_llm_dispatch_attempt_composition_boundaries() -> None:
    source = COMPOSITION_PATH.read_text(encoding="utf-8")

    forbidden = (
        "GroqDispatchExecutor",
        "GroqProviderAdapter",
        "LlmProviderPort",
        "ExecuteLlmTask",
        "ExecuteAndRecordLlmTask",
        "Groq",
        "qwen",
        "model_ref",
        "account_ref",
        "httpx",
        "requests",
        "os.environ",
        "GROQ_API_KEY",
        "knowledge_workbench",
        "artifact_runtime",
        "capacity_runtime",
    )
    for marker in forbidden:
        assert marker not in source


def test_dispatch_read_repository_boundaries() -> None:
    source = READ_REPOSITORY_PATH.read_text(encoding="utf-8")

    forbidden = (
        "llm_runtime",
        "Groq",
        "provider",
        "model_ref",
        "account_ref",
        "capacity_runtime",
        "knowledge_workbench",
        "artifact_runtime",
    )
    for marker in forbidden:
        assert marker not in source
