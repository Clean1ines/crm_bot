from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def _source() -> str:
    return (
        ROOT / "src/interfaces/composition/execute_prepared_llm_dispatch_attempt.py"
    ).read_text(encoding="utf-8")


def test_provider_rate_limit_does_not_write_work_item_retry_timer() -> None:
    source = _source()

    assert "next" + "_attempt" + "_at" not in source
    assert "RecordWorkItemAttemptOutcomeCommand" in source


def test_execute_bridge_keeps_capacity_metadata_separate_from_work_item_timing() -> (
    None
):
    source = _source()

    assert "capacity_observation" in source
    assert "WorkItemAttemptOutcomeStatus.RETRYABLE_FAILED" in source


def test_deferred_outcome_path_is_not_a_regular_execution_bridge_status() -> None:
    source = _source()

    assert "WorkItemAttemptOutcomeStatus." + "DEFERRED" not in source
    assert "LlmDispatchExecutionStatus." + "DEFERRED" not in source
