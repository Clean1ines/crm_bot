from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_entry_persistence_module_owns_entry_surface_write_sql() -> None:
    source = _read("src/infrastructure/db/repositories/knowledge_entry_persistence.py")

    required = [
        "def entry_embedding_text(",
        "def enrichment_payload(",
        "async def delete_retrieval_surface(",
        "async def update_retrieval_surface_metadata(",
        "async def update_retrieval_surface_content(",
        "async def delete_document_retrieval_surface(",
        "async def replace_entry_source_refs(",
        "async def replace_entry_source_refs_from_payload(",
        "async def sync_entry_retrieval_surface(",
        "async def upsert_retrieval_surface_from_payload(",
        "INSERT INTO knowledge_entry_source_refs",
        "INSERT INTO knowledge_retrieval_surface",
        "ON CONFLICT (entry_id)",
        "build_retrieval_surface_search_text",
    ]

    for marker in required:
        assert marker in source


def test_repository_delegates_canonical_entry_surface_persistence() -> None:
    repository = Path(
        "src/infrastructure/db/repositories/knowledge_repository.py"
    ).read_text(encoding="utf-8")
    entry_persistence = Path(
        "src/infrastructure/db/repositories/knowledge_entry_persistence.py"
    ).read_text(encoding="utf-8")
    curation_operations = Path(
        "src/infrastructure/db/repositories/knowledge_curation_entry_operations.py"
    ).read_text(encoding="utf-8")

    assert "sync_entry_retrieval_surface(" in repository
    assert "upsert_retrieval_surface_from_payload(" not in repository
    assert "upsert_retrieval_surface_from_payload(" in curation_operations

    assert "async def sync_entry_retrieval_surface(" in entry_persistence
    assert "async def upsert_retrieval_surface_from_payload(" in entry_persistence
    assert "INSERT INTO knowledge_retrieval_surface" in entry_persistence


def test_repository_delegates_retrieval_surface_delete_helper() -> None:
    repository = Path(
        "src/infrastructure/db/repositories/knowledge_repository.py"
    ).read_text(encoding="utf-8")
    entry_persistence = Path(
        "src/infrastructure/db/repositories/knowledge_entry_persistence.py"
    ).read_text(encoding="utf-8")
    curation_operations = Path(
        "src/infrastructure/db/repositories/knowledge_curation_entry_operations.py"
    ).read_text(encoding="utf-8")

    assert "delete_retrieval_surface(" in repository
    assert "delete_document_retrieval_surface(" in repository
    assert "update_retrieval_surface_metadata(" not in repository
    assert "update_retrieval_surface_metadata(" in curation_operations

    assert "async def delete_retrieval_surface(" in entry_persistence
    assert "async def delete_document_retrieval_surface(" in entry_persistence
    assert "async def update_retrieval_surface_metadata(" in entry_persistence
    assert "DELETE FROM knowledge_retrieval_surface" in entry_persistence
    assert "UPDATE knowledge_retrieval_surface" in entry_persistence


def test_repository_no_longer_owns_entry_surface_or_source_ref_mutation_sql() -> None:
    repository = _read("src/infrastructure/db/repositories/knowledge_repository.py")

    forbidden_sql_fragments = (
        "INSERT INTO knowledge_retrieval_surface",
        "UPDATE knowledge_retrieval_surface",
        "DELETE FROM knowledge_retrieval_surface",
        "INSERT INTO knowledge_entry_source_refs",
        "DELETE FROM knowledge_entry_source_refs",
    )

    for fragment in forbidden_sql_fragments:
        assert fragment not in repository
