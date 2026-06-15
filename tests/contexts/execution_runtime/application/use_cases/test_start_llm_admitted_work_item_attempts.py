from __future__ import annotations

from pathlib import Path


def test_started_attempt_ids_are_deterministic_from_work_item_attempt_count() -> None:
    source = Path(
        "src/interfaces/composition/start_llm_admitted_work_item_attempts.py",
    ).read_text(encoding="utf-8")

    assert (
        'attempt_id = f"{work_item.work_item_id}:attempt:{work_item.attempt_count}"'
        in source
    )


def test_postgres_attempt_dispatch_inserts_do_not_silently_ignore_conflicts() -> None:
    source = Path(
        "src/contexts/execution_runtime/infrastructure/postgres/"
        "postgres_work_item_attempt_dispatch_repository.py",
    ).read_text(encoding="utf-8")

    assert "ON CONFLICT" not in source
    assert "DO NOTHING" not in source
