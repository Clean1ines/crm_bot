from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]


def _source() -> str:
    return (
        ROOT / "src/contexts/execution_runtime/infrastructure/postgres/"
        "postgres_work_item_scheduling_repository.py"
    ).read_text(encoding="utf-8")


def test_scheduling_repository_does_not_persist_work_item_retry_timer() -> None:
    source = _source()

    assert "next" + "_attempt" + "_at" not in source
    assert "INSERT INTO execution_work_items" in source
    assert "last_error_kind" in source


def test_scheduling_repository_persists_payload_as_jsonb_from_json_dump() -> None:
    source = _source()

    assert "payload_json = json.dumps(" in source
    assert "$4::jsonb" in source
