from __future__ import annotations

from pathlib import Path


PATHS = (
    Path(
        "src/contexts/execution_runtime/application/ports/"
        "work_item_attempt_outcome_repository_port.py",
    ),
    Path(
        "src/contexts/execution_runtime/application/use_cases/"
        "record_work_item_attempt_outcome.py",
    ),
    Path(
        "src/contexts/execution_runtime/infrastructure/postgres/"
        "postgres_work_item_attempt_outcome_repository.py",
    ),
)


def test_execution_attempt_outcome_required_markers_exist() -> None:
    source = "\n".join(path.read_text(encoding="utf-8") for path in PATHS)

    required = (
        "RecordWorkItemAttemptOutcome",
        "WorkItemAttemptOutcomeRepositoryPort",
        "WorkItemAttemptOutcomeRecord",
        "WorkItemAttemptOutcomeStatus",
        "PostgresWorkItemAttemptOutcomeRepository",
        "record_attempt_outcome",
        "execution_work_item_attempts",
        "execution_work_items",
        "WorkItemStateMachine",
    )
    for marker in required:
        assert marker in source


def test_execution_attempt_outcome_remains_generic() -> None:
    source = "\n".join(path.read_text(encoding="utf-8") for path in PATHS)

    forbidden = (
        "llm_runtime",
        "capacity_runtime",
        "knowledge_workbench",
        "artifact_runtime",
        "Groq",
        "qwen",
        "provider",
        "model_ref",
        "account_ref",
        "httpx",
        "requests",
        "os.environ",
        "GROQ_API_KEY",
    )
    for marker in forbidden:
        assert marker not in source
