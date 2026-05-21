from __future__ import annotations

from pathlib import Path


def test_compiler_run_persistence_module_owns_compiler_trace_sql() -> None:
    helper_source = Path(
        "src/infrastructure/db/repositories/knowledge_compiler_run_persistence.py"
    ).read_text(encoding="utf-8")

    assert "INSERT INTO knowledge_compiler_runs" in helper_source
    assert "INSERT INTO knowledge_compiler_batches" in helper_source
    assert "UPDATE knowledge_compiler_batches" in helper_source
    assert "INSERT INTO knowledge_compilation_metrics" in helper_source
    assert "ON CONFLICT (compiler_run_id)" in helper_source


def test_repository_delegates_compiler_trace_persistence_sql() -> None:
    repository_source = Path(
        "src/infrastructure/db/repositories/knowledge_repository.py"
    ).read_text(encoding="utf-8")

    assert "await upsert_compiler_run(" in repository_source
    assert "await upsert_compiler_batch(" in repository_source
    assert "await persist_mark_compiler_batch_processing(" in repository_source
    assert "await persist_complete_compiler_batch(" in repository_source
    assert "await persist_fail_compiler_batch(" in repository_source
    assert "await persist_complete_compiler_run(" in repository_source
    assert "await persist_fail_compiler_run(" in repository_source

    assert "INSERT INTO knowledge_compiler_runs" not in repository_source
    assert "INSERT INTO knowledge_compiler_batches" not in repository_source
    assert "UPDATE knowledge_compiler_batches" not in repository_source
    assert "INSERT INTO knowledge_compilation_metrics" not in repository_source
    assert "ON CONFLICT (compiler_run_id)" not in repository_source
