from pathlib import Path


def test_ingestion_persists_source_chunks_for_compiled_documents() -> None:
    source = Path(
        "src/application/services/knowledge_structured_ingestion_service.py"
    ).read_text(encoding="utf-8")

    assert "await repo.add_source_chunks(" in source
    assert "source_chunks=source_chunks" in source or "chunks=source_chunks" in source
    assert "MODE_PRICE_LIST" in source
    assert "CommercialPriceIngestionService" in source


def test_plain_source_chunk_ingestion_path_is_removed() -> None:
    source = Path("src/application/services/knowledge_ingestion_service.py").read_text(
        encoding="utf-8"
    )

    assert "MODE_PLAIN" not in source
    assert "plain_upload" not in source
