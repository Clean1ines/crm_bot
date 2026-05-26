from src.interfaces.composition.knowledge_upload import make_knowledge_preprocessor


def test_make_knowledge_preprocessor_forbids_faq_mode() -> None:
    try:
        make_knowledge_preprocessor(preprocessing_mode="faq")
    except ValueError as exc:
        assert "forbidden" in str(exc).lower()
    else:
        raise AssertionError("Expected ValueError for faq mode")


def test_make_knowledge_preprocessor_allows_non_faq_mode() -> None:
    preprocessor = make_knowledge_preprocessor(preprocessing_mode="plain")
    assert preprocessor.model_name
