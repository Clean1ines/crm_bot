import pytest

from src.interfaces.http.knowledge import make_knowledge_preprocessor


def test_http_make_knowledge_preprocessor_forbids_faq_mode() -> None:
    with pytest.raises(ValueError):
        make_knowledge_preprocessor(preprocessing_mode="faq")


def test_http_make_knowledge_preprocessor_allows_non_faq_mode() -> None:
    preprocessor = make_knowledge_preprocessor(preprocessing_mode="plain")
    assert preprocessor.model_name
