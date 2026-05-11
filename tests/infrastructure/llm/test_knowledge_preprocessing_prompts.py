from __future__ import annotations

from pathlib import Path


PROMPT_DIR = Path("src/agent/prompts")


def test_preprocessing_prompts_require_dense_query_surface() -> None:
    for file_name in (
        "knowledge_preprocess_faq.txt",
        "knowledge_preprocess_price_list.txt",
        "knowledge_preprocess_instruction.txt",
    ):
        text = (PROMPT_DIR / file_name).read_text(encoding="utf-8")

        assert "Every entry MUST have at least 3" in text
        assert "Every entry MUST have at least 5" in text
        assert "Every entry MUST have at least 2 tags" in text
        assert "embedding_text MUST include" in text
        assert "source_excerpt" in text
        assert "Do not invent" in text or "Do NOT generalize" in text
