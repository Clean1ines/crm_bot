from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_source_chunk_persistence_preserves_empty_section_title() -> None:
    repository_source = (
        ROOT / "src/infrastructure/db/repositories/knowledge_repository.py"
    ).read_text(encoding="utf-8")
    helper_source = (
        ROOT
        / "src/infrastructure/db/repositories/knowledge_source_chunk_persistence.py"
    ).read_text(encoding="utf-8")

    assert "await replace_document_source_chunks(" in repository_source
    assert "INSERT INTO knowledge_source_chunks" not in repository_source
    assert "chunk.section_title or None" not in helper_source
    assert "chunk.section_title," in helper_source


def test_source_chunk_repository_preserves_empty_section_title() -> None:
    repository_source = (
        ROOT / "src/infrastructure/db/repositories/knowledge_repository.py"
    ).read_text(encoding="utf-8")
    helper_source = (
        ROOT
        / "src/infrastructure/db/repositories/knowledge_source_chunk_persistence.py"
    ).read_text(encoding="utf-8")

    assert "await replace_document_source_chunks(" in repository_source
    assert "INSERT INTO knowledge_source_chunks" not in repository_source
    assert "chunk.section_title or None" not in helper_source
    assert "chunk.section_title," in helper_source
