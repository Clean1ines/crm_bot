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
    source = _read("src/application/ports/knowledge/canonical_entries.py")
    aggregate_source = _read("src/application/ports/knowledge_port.py")

    assert "CanonicalKnowledgeEntry" in source
    assert "add_canonical_entries" in source
    assert "add_knowledge_chunks" not in source
    assert "from src.domain.project_plane.knowledge_chunks import" not in source
    assert "chunks: Sequence[KnowledgeChunk]" not in source

    assert "KnowledgeCanonicalEntryPort" in aggregate_source
    assert "CanonicalKnowledgeEntry" not in aggregate_source
    assert "add_canonical_entries" not in aggregate_source
    assert "add_knowledge_chunks" not in aggregate_source
    assert (
        "from src.domain.project_plane.knowledge_chunks import" not in aggregate_source
    )
    assert "chunks: Sequence[KnowledgeChunk]" not in aggregate_source


def test_structured_ingestion_writes_source_chunks_then_canonical_entries() -> None:
    facade_source = _read("src/application/services/knowledge_ingestion_service.py")
    structured_source = _read(
        "src/application/services/knowledge_structured_ingestion_service.py"
    )
    publication_source = _read(
        "src/application/services/knowledge_stage_k_shared_helpers.py"
    )
    canonical_builder_source = _read(
        "src/application/services/knowledge_canonical_publication_builder.py"
    )

    assert "KnowledgeStructuredIngestionService" in facade_source
    assert "repo.add_knowledge_chunks" not in facade_source

    assert "repo.add_source_chunks" in structured_source
    assert "canonical_entries_from_preprocessing_result" in structured_source
    assert "repo.add_knowledge_chunks" not in structured_source

    assert "repo.add_canonical_entries" in publication_source
    assert "CanonicalKnowledgeEntry(" in canonical_builder_source
    assert "KnowledgeEntryStatus.PUBLISHED" in canonical_builder_source
    assert "KnowledgeEntryVisibility.RUNTIME" in canonical_builder_source


def test_runtime_retrieval_reads_retrieval_surface_not_knowledge_base() -> None:
    repository = _read("src/infrastructure/db/repositories/knowledge_repository.py")
    queries = _read("src/infrastructure/db/repositories/knowledge_search_queries.py")

    search_block = repository[
        repository.index("    async def search(") : repository.index(
            "    async def preview_search("
        )
    ]

    assert "RUNTIME_HYBRID_SEARCH_SQL" in search_block
    assert "RUNTIME_VECTOR_SEARCH_SQL" in search_block
    assert "knowledge_base" not in search_block
    assert "chunk_type" not in search_block
    assert "entry_type" not in search_block

    assert "knowledge_retrieval_surface AS rs" in queries
    assert "rs.entry_kind = ANY" in queries
    assert "rs.status = 'published'" in queries
    assert "rs.visibility = 'runtime'" in queries
    assert "knowledge_base" not in queries
    assert "chunk_type" not in queries
    assert "entry_type" not in queries


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
    cleanup_only_exceptions = {
        "src/domain/project_plane/knowledge_artifact_cleanup.py",
        "src/infrastructure/db/repositories/knowledge_artifact_cleanup.py",
    }

    offenders: list[str] = []
    for path in (ROOT / "src").rglob("*.py"):
        rel = path.relative_to(ROOT).as_posix()
        if rel in cleanup_only_exceptions:
            continue

        text = path.read_text(encoding="utf-8")
        if "knowledge_base" in text:
            offenders.append(rel)

    assert offenders == []
