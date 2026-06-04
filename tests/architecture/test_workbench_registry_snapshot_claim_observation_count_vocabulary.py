from pathlib import Path


CHECKED = (
    Path("src/domain/project_plane/knowledge_workbench/registry.py"),
    Path("src/infrastructure/db/knowledge_workbench_repository.py"),
    Path("src/application/services/faq_workbench_fresh_upload_service.py"),
    Path("src/application/services/faq_workbench_claim_observations_service.py"),
    Path("src/application/services/faq_workbench_registry_application_service.py"),
    Path("src/infrastructure/llm/faq_workbench_final_reconciliation_generator.py"),
)

MIGRATIONS = tuple(Path("migrations").glob("*.sql"))

FORBIDDEN = ("finding_count",)

REQUIRED = ("claim_observation_count",)


def _read(paths: tuple[Path, ...]) -> str:
    return "\n".join(
        path.read_text(encoding="utf-8") for path in paths if path.exists()
    )


def test_registry_snapshot_code_uses_claim_observation_count() -> None:
    source = _read(CHECKED)

    for token in REQUIRED:
        assert token in source

    for token in FORBIDDEN:
        assert token not in source


def test_active_migrations_use_claim_observation_count_not_finding_count() -> None:
    source = _read(MIGRATIONS)

    assert "claim_observation_count" in source
    assert "finding_count" not in source
