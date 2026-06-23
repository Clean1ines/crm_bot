from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def _source() -> str:
    return (
        ROOT / "src/interfaces/composition/prepare_llm_dispatch_batch.py"
    ).read_text(encoding="utf-8")


def test_prepare_batch_has_no_work_item_retry_timer_admission_filter() -> None:
    source = _source()

    assert "next" + "_attempt" + "_at" not in source
    assert "lease_due_work_item" in source


def test_capacity_retry_at_remains_command_capacity_wakeup_not_work_item_field() -> (
    None
):
    source = _source()

    assert "capacity_retry_at" in source
    assert "WorkflowCommand" not in source or "run_after" not in source
