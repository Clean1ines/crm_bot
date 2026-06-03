from pathlib import Path


CHECKED = (
    Path("src/domain/project_plane/knowledge_workbench/registry.py"),
    Path("src/infrastructure/db/knowledge_workbench_repository.py"),
    Path("src/application/services/faq_workbench_registry_application_service.py"),
    Path("src/application/services/faq_workbench_registry_application_work_item_processor_service.py"),
)

ACTIVE_MIGRATIONS = tuple(Path("migrations").glob("*.sql"))

FORBIDDEN = (
    "target_registry_entry_id",
)

REQUIRED = (
    "target_fact_id",
)


def _read(paths: tuple[Path, ...]) -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in paths if path.exists())


def test_registry_application_code_uses_target_fact_id() -> None:
    source = _read(CHECKED)

    for token in REQUIRED:
        assert token in source

    for token in FORBIDDEN:
        assert token not in source


def test_active_migrations_use_target_fact_id_not_target_registry_entry_id() -> None:
    source = _read(ACTIVE_MIGRATIONS)

    assert "target_fact_id" in source
    assert "target_registry_entry_id" not in source
