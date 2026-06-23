from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]


def _source() -> str:
    return (
        ROOT / "src/contexts/execution_runtime/infrastructure/postgres/"
        "postgres_work_item_attempt_outcome_repository.py"
    ).read_text(encoding="utf-8")


def test_attempt_outcome_repository_has_no_work_item_retry_timer_column() -> None:
    source = _source()

    assert "next" + "_attempt" + "_at" not in source
    assert "WorkItemAttemptOutcomeStatus." + "DEFERRED" not in source


def test_attempt_outcome_repository_keeps_retryable_failure_as_immediate_state() -> (
    None
):
    source = _source()

    assert "fail_leased_retryable" in source
    assert "retry_plan" in source


def test_repository_has_no_llm_or_capacity_runtime_imports() -> None:
    source = _source()

    assert "llm_runtime" not in source
    assert "capacity_runtime" not in source
