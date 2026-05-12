from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_stage_cd_migration_declares_canonical_entries_source_refs_and_surface() -> (
    None
):
    migration = _read(
        "migrations/059_create_knowledge_entries_and_retrieval_surface.sql"
    )

    assert "CREATE TABLE IF NOT EXISTS knowledge_entries" in migration
    assert "CREATE TABLE IF NOT EXISTS knowledge_entry_source_refs" in migration
    assert "CREATE TABLE IF NOT EXISTS knowledge_retrieval_surface" in migration
    assert (
        "source_chunk_id TEXT NOT NULL REFERENCES knowledge_source_chunks" in migration
    )
    assert "embedding vector(384)" in migration
    assert "status = 'published'" in migration
    assert "visibility = 'runtime'" in migration


def test_application_port_exposes_canonical_entry_write_not_legacy_chunk_write() -> (
    None
):
    source = _read("src/application/ports/knowledge_port.py")

    assert "CanonicalKnowledgeEntry" in source
    assert "add_canonical_entries" in source
    assert "add_knowledge_chunks" not in source
    assert "from src.domain.project_plane.knowledge_chunks import" not in source
    assert "chunks: Sequence[KnowledgeChunk]" not in source


def test_ingestion_writes_source_chunks_then_canonical_entries() -> None:
    source = _read("src/application/services/knowledge_ingestion_service.py")

    assert "repo.add_source_chunks" in source
    assert "repo.add_canonical_entries" in source
    assert "CanonicalKnowledgeEntry(" in source
    assert "KnowledgeEntryStatus.PUBLISHED" in source
    assert "KnowledgeEntryVisibility.RUNTIME" in source
    assert "repo.add_knowledge_chunks" not in source


def test_runtime_retrieval_reads_retrieval_surface_not_knowledge_base() -> None:
    source = _read("src/infrastructure/db/repositories/knowledge_repository.py")
    search_block = source[
        source.index("    async def search(") : source.index(
            "    async def preview_search("
        )
    ]
    preview_block = source[
        source.index("    async def preview_search(") : source.index(
            "    async def add_canonical_entries("
        )
    ]

    assert "knowledge_retrieval_surface AS rs" in search_block
    assert "knowledge_retrieval_surface AS rs" in preview_block
    assert "knowledge_base" not in search_block
    assert "knowledge_base" not in preview_block


def test_rag_eval_loads_retrieval_surface_not_knowledge_base() -> None:
    source = _read("src/infrastructure/db/repositories/rag_eval_repository.py")
    load_block = source[
        source.index("    async def load_document_entries(") : source.index(
            "    async def save_dataset("
        )
    ]

    assert "knowledge_retrieval_surface AS rs" in load_block
    assert "knowledge_base" not in load_block


def test_active_src_has_no_legacy_knowledge_base_runtime_paths() -> None:
    offenders: list[str] = []
    for path in (ROOT / "src").rglob("*.py"):
        rel = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        if "knowledge_base" in text:
            offenders.append(rel)

    assert offenders == []
