from __future__ import annotations

import pytest

from src.domain.project_plane.knowledge_preprocessing import (
    MODE_FAQ,
    KnowledgePreprocessingValidationError,
    parse_preprocessing_payload,
)


def test_parse_preprocessing_payload_forbids_legacy_faq_fragments() -> None:
    with pytest.raises(KnowledgePreprocessingValidationError, match="forbidden"):
        parse_preprocessing_payload(
            {"fragments": []},
            mode=MODE_FAQ,
            model="test-model",
            prompt_version="legacy",
        )
