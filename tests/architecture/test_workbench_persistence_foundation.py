from __future__ import annotations

import re
from pathlib import Path


WORKBENCH_REPOSITORIES = (
    Path("src/infrastructure/db/knowledge_workbench_repository.py"),
    Path("src/infrastructure/db/workbench_observability_repository.py"),
)
MIGRATION = Path("migrations/070_create_faq_workbench_v1.sql")


def _table_refs(source: str) -> set[str]:
    tables: set[str] = set()
    for pattern in (
        r"FROM\s+(knowledge_[a-zA-Z0-9_]+)",
        r"INSERT\s+INTO\s+(knowledge_[a-zA-Z0-9_]+)",
        r"UPDATE\s+(knowledge_[a-zA-Z0-9_]+)",
        r"DELETE\s+FROM\s+(knowledge_[a-zA-Z0-9_]+)",
    ):
        tables.update(re.findall(pattern, source, flags=re.IGNORECASE))
    return tables


def _migration_tables() -> set[str]:
    source = MIGRATION.read_text(encoding="utf-8")
    return set(
        re.findall(
            r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+([a-zA-Z0-9_]+)",
            source,
            flags=re.IGNORECASE,
        )
    )


def test_workbench_repositories_use_only_first_class_workbench_tables() -> None:
    for path in WORKBENCH_REPOSITORIES:
        refs = _table_refs(path.read_text(encoding="utf-8"))
        assert refs
        assert "knowledge_documents" not in refs
        assert "knowledge_document_sections" not in refs
        assert "knowledge_processing_runs" not in refs
        assert "knowledge_processing_node_runs" not in refs
        assert all(table.startswith("knowledge_workbench_") for table in refs)


def test_every_workbench_repository_table_is_backed_by_migration() -> None:
    refs: set[str] = set()
    for path in WORKBENCH_REPOSITORIES:
        refs.update(_table_refs(path.read_text(encoding="utf-8")))

    assert sorted(refs.difference(_migration_tables())) == []


def test_workbench_document_migration_preserves_donor_document_metadata() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    required_columns = (
        "document_id TEXT PRIMARY KEY",
        "storage_id UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE",
        "file_size_bytes BIGINT NOT NULL DEFAULT 0",
        "status TEXT NOT NULL",
        "uploaded_by_user_id TEXT",
        "uploaded_by_actor_type TEXT NOT NULL DEFAULT 'unknown'",
        "uploaded_by_actor_id TEXT",
        "trusted_upload BOOLEAN NOT NULL DEFAULT FALSE",
        "last_error_kind TEXT",
        "last_error_message TEXT",
        "last_error_at TIMESTAMPTZ",
        "created_at TIMESTAMPTZ NOT NULL DEFAULT now()",
        "updated_at TIMESTAMPTZ NOT NULL DEFAULT now()",
        "deleted_at TIMESTAMPTZ",
    )

    for marker in required_columns:
        assert marker in source
