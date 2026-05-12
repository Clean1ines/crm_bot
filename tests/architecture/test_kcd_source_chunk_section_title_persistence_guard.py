from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_source_chunk_section_title_schema_is_not_null_with_empty_default() -> None:
    migration = (ROOT / "migrations/058_create_knowledge_source_chunks.sql").read_text(
        encoding="utf-8"
    )

    assert "section_title TEXT NOT NULL DEFAULT ''" in migration


def test_source_chunk_repository_preserves_empty_section_title() -> None:
    repository = (
        ROOT / "src/infrastructure/db/repositories/knowledge_repository.py"
    ).read_text(encoding="utf-8")

    match = re.search(
        r"async def add_source_chunks\(.*?\n        return len\(chunks\)",
        repository,
        flags=re.DOTALL,
    )
    assert match is not None

    add_source_chunks_body = match.group(0)

    assert "chunk.section_title or None" not in add_source_chunks_body
    assert re.search(
        r"chunk\.page,\s*\n\s*chunk\.section_title,\s*\n\s*chunk\.start_offset,",
        add_source_chunks_body,
    )
