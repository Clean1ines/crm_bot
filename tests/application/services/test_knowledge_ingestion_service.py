from pathlib import Path


def test_direct_knowledge_ingestion_service_rejects_faq_mode() -> None:
    source = Path("src/application/services/knowledge_ingestion_service.py").read_text(
        encoding="utf-8"
    )

    assert "if mode == MODE_FAQ:" in source
    assert "Bootstrap FAQ surface path was removed from the primary pipeline" in source
    assert (
        "FAQ uploads must use KnowledgeSurfaceCompilerPort.compile_surfaces" in source
    )


def test_direct_knowledge_ingestion_service_requires_price_list_preprocessor() -> None:
    source = Path("src/application/services/knowledge_ingestion_service.py").read_text(
        encoding="utf-8"
    )

    assert (
        "Knowledge preprocessing adapter is required for price_list uploads" in source
    )
    assert "preprocessor_factory is None" in source


def test_direct_knowledge_ingestion_service_no_longer_has_plain_runtime_branch() -> (
    None
):
    source = Path("src/application/services/knowledge_ingestion_service.py").read_text(
        encoding="utf-8"
    )

    assert "MODE_PLAIN" not in source
    assert "PREPROCESSING_STATUS_NOT_REQUESTED" not in source
    assert "plain_upload" not in source


def test_direct_knowledge_ingestion_service_still_preserves_price_list_path() -> None:
    source = Path("src/application/services/knowledge_ingestion_service.py").read_text(
        encoding="utf-8"
    )

    assert "MODE_PRICE_LIST" in source
    assert "preprocessor_factory" in source
    assert "KnowledgePreprocessorPort" in source
    assert "add_canonical_entries" in source
