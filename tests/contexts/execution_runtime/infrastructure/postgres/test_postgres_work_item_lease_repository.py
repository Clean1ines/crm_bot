from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]


def _source() -> str:
    return (
        ROOT / "src/contexts/execution_runtime/infrastructure/postgres/"
        "postgres_work_item_lease_repository.py"
    ).read_text(encoding="utf-8")


def test_peek_due_work_items_has_no_time_filter() -> None:
    source = _source()

    assert "next" + "_attempt" + "_at" not in source
    assert "available_at" not in source
    assert "deferred_until" not in source
    assert "not_before" not in source


def test_retryable_failed_work_items_are_prioritized_before_ready() -> None:
    source = _source()

    assert "retryable_failed" in source
    assert "ready" in source
    assert "CASE wi.status" in source or "CASE" in source


def test_lease_repository_forbids_deferred_due_selection() -> None:
    source = _source()

    assert "'deferred'" not in source
    assert "WorkItemStatus." + "DEFERRED" not in source


def test_lease_repository_exposes_targeted_lease_by_work_item_id() -> None:
    source = _source()

    assert "lease_due_work_item_by_id" in source
    assert "wi.work_item_id = $2" in source
    assert "FOR UPDATE SKIP LOCKED" in source
    assert "LIMIT 1" in source


def test_work_item_lease_port_exposes_targeted_lease_by_work_item_id() -> None:
    port_source = (
        ROOT / "src/contexts/execution_runtime/application/ports/"
        "work_item_lease_repository_port.py"
    ).read_text(encoding="utf-8")

    assert "lease_due_work_item_by_id" in port_source
    assert "work_item_id: str" in port_source
    assert "LeasedWorkItemRecord | None" in port_source
