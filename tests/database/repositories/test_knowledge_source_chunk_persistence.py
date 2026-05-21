from __future__ import annotations

from pathlib import Path


def test_source_chunk_persistence_module_owns_source_chunk_sql() -> None:
    helper_source = Path(
        "src/infrastructure/db/repositories/knowledge_source_chunk_persistence.py"
    ).read_text(encoding="utf-8")

    assert "FROM knowledge_source_chunks" in helper_source
    assert "DELETE FROM knowledge_source_chunks WHERE document_id = $1" in helper_source
    assert "INSERT INTO knowledge_source_chunks" in helper_source
    assert "ON CONFLICT (id) DO UPDATE SET" in helper_source
    assert "chunk.section_title," in helper_source
    assert "chunk.section_title or None" not in helper_source


def test_repository_delegates_source_chunk_sql() -> None:
    repository_source = Path(
        "src/infrastructure/db/repositories/knowledge_repository.py"
    ).read_text(encoding="utf-8")

    assert "await query_document_source_chunks(" in repository_source
    assert "await replace_document_source_chunks(" in repository_source
    assert "await delete_document_source_chunks(" in repository_source

    assert "FROM knowledge_source_chunks" not in repository_source
    assert "DELETE FROM knowledge_source_chunks WHERE document_id = $1" not in (
        repository_source
    )
    assert "INSERT INTO knowledge_source_chunks" not in repository_source
