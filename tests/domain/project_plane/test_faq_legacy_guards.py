from __future__ import annotations

import pytest

from src.domain.project_plane.knowledge_preprocessing import (
    MODE_FAQ,
    KnowledgePreprocessingValidationError,
    parse_preprocessing_payload,
)


def test_parse_preprocessing_payload_forbids_legacy_faq_fragments() -> None:
    with pytest.raises(
        KnowledgePreprocessingValidationError,
        match="retrieval surface compiler",
    ):
        parse_preprocessing_payload(
            {"fragments": []},
            mode=MODE_FAQ,
            model="test-model",
            prompt_version="legacy",
        )


def test_parse_preprocessing_payload_allows_non_faq_legacy_path() -> None:
    result = parse_preprocessing_payload(
        {
            "fragments": [
                {
                    "canonical_question": "Что это?",
                    "answer": "Ответ",
                    "source_excerpt": "Фрагмент",
                    "source_chunk_ids": [0],
                }
            ]
        },
        mode="plain",
        model="test-model",
        prompt_version="legacy",
    )

    assert len(result.entries) == 1
    assert result.entries[0].questions[0] == "Что это?"
