from pathlib import Path

from src.domain.project_plane.knowledge_entry_kind import (
    RUNTIME_ENTRY_KIND_VALUES,
)


MIGRATION_PATH = Path("migrations/079_add_faq_workbench_fact_runtime_entry_kind.sql")
KNOWLEDGE_REPOSITORY_PATH = Path(
    "src/infrastructure/db/repositories/knowledge_repository.py"
)


def test_faq_workbench_fact_is_answerable_runtime_entry_kind() -> None:
    assert "faq_workbench_fact" in RUNTIME_ENTRY_KIND_VALUES


def test_faq_workbench_fact_is_allowed_by_database_entry_kind_constraint() -> None:
    migration_source = MIGRATION_PATH.read_text()

    assert "'faq_workbench_fact'" in migration_source
    assert "ck_knowledge_entries_entry_kind" in migration_source


def test_knowledge_repository_search_uses_answerable_entry_kind_values() -> None:
    source = KNOWLEDGE_REPOSITORY_PATH.read_text()

    assert (
        "ANSWERABLE_KNOWLEDGE_ENTRY_KINDS = tuple(sorted(RUNTIME_ENTRY_KIND_VALUES))"
        in source
    )
    assert "list(ANSWERABLE_KNOWLEDGE_ENTRY_KINDS)" in source
