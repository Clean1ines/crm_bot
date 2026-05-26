from __future__ import annotations

import pytest

from src.domain.project_plane.knowledge_preprocessing import MODE_FAQ
from src.infrastructure.llm.knowledge_preprocessor import _load_mode_prompt


def test_load_mode_prompt_forbids_legacy_faq_prompt_selection() -> None:
    with pytest.raises(Exception, match="faq|FAQ"):
        _load_mode_prompt(MODE_FAQ)
