from __future__ import annotations

from pathlib import Path


def test_source_units_jsonb_values_are_serialized_for_asyncpg() -> None:
    source = Path(
        "src/contexts/knowledge_workbench/source_management/infrastructure/postgres/"
        "postgres_source_management_repository.py",
    ).read_text(encoding="utf-8")

    assert "import json" in source
    assert "json.dumps(list(unit.heading_path.parts))" in source
    assert '"parent_refs"' in source
    assert "json.dumps(" in source
    assert "list(unit.heading_path.parts)," not in source
    assert "decoded = json.loads(value)" in source


def test_progress_endpoint_does_not_import_deleted_composition() -> None:
    source = Path("src/interfaces/http/knowledge.py").read_text(encoding="utf-8")

    forbidden = (
        "faq_workbench_progress",
        "WorkbenchProgressNotFoundError",
        "fetch_workbench_progress",
    )

    for marker in forbidden:
        assert marker not in source

    required = (
        "async def knowledge_processing_progress",
        "PostgresSourceManagementRepository(pool)",
        "source_repository.load_source_document(document_ref)",
        "source_repository.list_source_units_for_document(document_ref)",
        "PostgresKnowledgeExtractionSagaStateRepository(pool)",
        '"progress_percent": progress_percent',
        '"metrics": metrics',
    )

    for marker in required:
        assert marker in source
