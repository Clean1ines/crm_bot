from __future__ import annotations

from pathlib import Path


def test_saga_phase_checkpoint_jsonb_payload_is_serialized_for_asyncpg() -> None:
    source = Path(
        "src/contexts/knowledge_workbench/infrastructure/postgres/"
        "postgres_knowledge_extraction_saga_state_repository.py",
    ).read_text(encoding="utf-8")

    assert "import json" in source
    assert "json.dumps(dict(checkpoint.checkpoint_payload))" in source
    assert "dict(checkpoint.checkpoint_payload)," not in source


def test_import_quality_endpoint_does_not_import_deleted_composition() -> None:
    source = Path("src/interfaces/http/knowledge.py").read_text(encoding="utf-8")

    forbidden = (
        "faq_workbench_import_quality",
        "WorkbenchImportQualityNotFoundError",
        "fetch_workbench_import_quality_report",
    )

    for marker in forbidden:
        assert marker not in source

    required = (
        "async def knowledge_import_quality_report",
        "PostgresSourceManagementRepository(pool)",
        "repository.load_source_document(document_ref)",
        "repository.list_source_units_for_document(document_ref)",
        '"source_units_count": source_units_count',
        '"safe_to_compile": safe_to_compile',
    )

    for marker in required:
        assert marker in source
