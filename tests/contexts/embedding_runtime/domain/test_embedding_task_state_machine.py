from __future__ import annotations

from pathlib import Path

import pytest

from src.contexts.embedding_runtime.domain.entities.embedding_task import EmbeddingTask
from src.contexts.embedding_runtime.domain.state_machines.embedding_task_state_machine import (
    EmbeddingTaskStateMachine,
    InvalidEmbeddingTaskTransition,
)
from src.contexts.embedding_runtime.domain.value_objects.embedding_input_ref import (
    EmbeddingInputRef,
)
from src.contexts.embedding_runtime.domain.value_objects.embedding_model_id import (
    EmbeddingModelId,
)
from src.contexts.embedding_runtime.domain.value_objects.embedding_task_status import (
    EmbeddingTaskStatus,
)


ROOT = Path(__file__).resolve().parents[4]
EMBEDDING_RUNTIME_DOMAIN = ROOT / "src" / "contexts" / "embedding_runtime" / "domain"


def _task(
    *,
    status: EmbeddingTaskStatus = EmbeddingTaskStatus.READY,
    last_error_kind: str | None = None,
) -> EmbeddingTask:
    return EmbeddingTask(
        task_id="embedding-task-1",
        input_ref=EmbeddingInputRef("draft-claim-1"),
        model_id=EmbeddingModelId("text-embedding-model"),
        status=status,
        last_error_kind=last_error_kind,
    )


def test_embedding_task_defaults_to_ready() -> None:
    task = _task()

    assert task.status is EmbeddingTaskStatus.READY
    assert task.last_error_kind is None


def test_embedding_task_rejects_empty_task_id() -> None:
    with pytest.raises(ValueError):
        EmbeddingTask(
            task_id=" ",
            input_ref=EmbeddingInputRef("draft-claim-1"),
            model_id=EmbeddingModelId("text-embedding-model"),
        )


def test_start_ready_marks_task_running() -> None:
    running = EmbeddingTaskStateMachine.start_ready(_task())

    assert running.status is EmbeddingTaskStatus.RUNNING
    assert running.last_error_kind is None


def test_succeed_running_marks_task_succeeded() -> None:
    running = EmbeddingTaskStateMachine.start_ready(_task())

    succeeded = EmbeddingTaskStateMachine.succeed_running(running)

    assert succeeded.status is EmbeddingTaskStatus.SUCCEEDED
    assert succeeded.status.is_terminal
    assert succeeded.last_error_kind is None


def test_fail_running_retryable_records_error_kind() -> None:
    running = EmbeddingTaskStateMachine.start_ready(_task())

    failed = EmbeddingTaskStateMachine.fail_running_retryable(
        running,
        error_kind="minute_limit",
    )

    assert failed.status is EmbeddingTaskStatus.RETRYABLE_FAILED
    assert failed.last_error_kind == "minute_limit"


def test_fail_running_terminal_records_error_kind() -> None:
    running = EmbeddingTaskStateMachine.start_ready(_task())

    failed = EmbeddingTaskStateMachine.fail_running_terminal(
        running,
        error_kind="unsupported_input",
    )

    assert failed.status is EmbeddingTaskStatus.TERMINAL_FAILED
    assert failed.status.is_terminal
    assert failed.last_error_kind == "unsupported_input"


def test_reset_retryable_to_ready_clears_error_kind() -> None:
    running = EmbeddingTaskStateMachine.start_ready(_task())
    retryable_failed = EmbeddingTaskStateMachine.fail_running_retryable(
        running,
        error_kind="minute_limit",
    )

    ready = EmbeddingTaskStateMachine.reset_retryable_to_ready(retryable_failed)

    assert ready.status is EmbeddingTaskStatus.READY
    assert ready.last_error_kind is None


def test_invalid_transitions_rejected() -> None:
    ready = _task()

    with pytest.raises(InvalidEmbeddingTaskTransition):
        EmbeddingTaskStateMachine.succeed_running(ready)

    with pytest.raises(InvalidEmbeddingTaskTransition):
        EmbeddingTaskStateMachine.fail_running_retryable(
            ready,
            error_kind="minute_limit",
        )

    succeeded = EmbeddingTaskStateMachine.succeed_running(
        EmbeddingTaskStateMachine.start_ready(ready)
    )

    with pytest.raises(InvalidEmbeddingTaskTransition):
        EmbeddingTaskStateMachine.start_ready(succeeded)


def test_error_kind_must_be_non_empty() -> None:
    running = EmbeddingTaskStateMachine.start_ready(_task())

    with pytest.raises(ValueError):
        EmbeddingTaskStateMachine.fail_running_retryable(running, error_kind=" ")


def test_failed_task_requires_error_kind() -> None:
    with pytest.raises(ValueError):
        _task(status=EmbeddingTaskStatus.RETRYABLE_FAILED)


def test_non_failed_task_rejects_error_kind() -> None:
    with pytest.raises(ValueError):
        _task(status=EmbeddingTaskStatus.READY, last_error_kind="unexpected")


def test_embedding_runtime_domain_has_no_provider_db_or_workbench_semantics() -> None:
    forbidden_markers = (
        "provider",
        "Groq",
        "groq",
        "Qwen",
        "qwen",
        "Postgres",
        "postgres",
        "pgvector",
        "knowledge_workbench",
        "DraftClaim",
        "Claim",
        "Surface",
        "surface",
    )

    offenders: list[str] = []
    for path in EMBEDDING_RUNTIME_DOMAIN.rglob("*.py"):
        if path.name == "__init__.py":
            continue
        text = path.read_text(encoding="utf-8")
        for marker in forbidden_markers:
            if marker in text:
                offenders.append(f"{path.relative_to(ROOT)} contains {marker!r}")

    assert not offenders
