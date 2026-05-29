from pathlib import Path


def test_knowledge_upload_queue_handler_routes_faq_to_service_pipeline() -> None:
    source = Path("src/infrastructure/queue/handlers/knowledge_upload.py").read_text(
        encoding="utf-8"
    )

    assert "mode == MODE_FAQ" in source
    assert "KnowledgeFaqSurfaceIngestionService" in source
    assert "GroqQualityGatedKnowledgeSurfaceCompiler" in source
    assert "process_document(" in source
    assert "KnowledgeStructuredIngestionService" in source

    faq_branch = source.split("mode == MODE_FAQ", 1)[1].split(
        "KnowledgeStructuredIngestionService", 1
    )[0]
    assert "process_document(" in faq_branch
    assert "return" in faq_branch
