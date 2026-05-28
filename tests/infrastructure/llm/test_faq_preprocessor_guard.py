from __future__ import annotations

import pytest

from src.domain.project_plane.knowledge_preprocessing import (
    MODE_FAQ,
    KnowledgePreprocessingValidationError,
)
from src.infrastructure.llm.knowledge_preprocessor import GroqKnowledgePreprocessor


@pytest.mark.asyncio
async def test_groq_preprocessor_preprocess_forbids_faq_mode() -> None:
    preprocessor = GroqKnowledgePreprocessor()
    with pytest.raises(KnowledgePreprocessingValidationError, match="forbidden"):
        await preprocessor.preprocess(mode=MODE_FAQ, chunks=[], file_name="faq.md")
