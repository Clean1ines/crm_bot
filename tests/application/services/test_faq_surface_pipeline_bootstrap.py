from pathlib import Path


def test_legacy_faq_bootstrap_path_is_removed_from_primary_ingestion() -> None:
    source = Path("src/application/services/knowledge_ingestion_service.py").read_text(
        encoding="utf-8"
    )

    assert "Bootstrap FAQ surface path was removed from the primary pipeline" in source
    assert "KnowledgeFaqSurfaceIngestionService" in source
    assert "KnowledgeSurfaceCompilerPort.compile_surfaces" in source


def test_queue_handler_routes_faq_to_surface_ingestion_service() -> None:
    source = Path("src/infrastructure/queue/handlers/knowledge_upload.py").read_text(
        encoding="utf-8"
    )

    faq_branch = source.split("mode == MODE_FAQ", 1)[1].split(
        "KnowledgeStructuredIngestionService", 1
    )[0]
    assert "KnowledgeFaqSurfaceIngestionService" in faq_branch
    assert "GroqQualityGatedKnowledgeSurfaceCompiler" in faq_branch
    assert "process_document(" in faq_branch
    assert "return" in faq_branch
