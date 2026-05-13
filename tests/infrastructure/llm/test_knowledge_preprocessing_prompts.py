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


def test_semantic_merge_tightening_prompt_is_group_scoped_and_strict() -> None:
    from src.domain.project_plane.knowledge_preprocessing import (
        MODE_FAQ,
        KnowledgeSemanticMergeCandidate,
        KnowledgeSemanticMergeGroup,
    )
    from src.infrastructure.llm.knowledge_preprocessor import GroqKnowledgePreprocessor

    preprocessor = GroqKnowledgePreprocessor(client=object(), model="test-model")
    prompt = preprocessor._build_semantic_merge_tightening_prompt(
        mode=MODE_FAQ,
        file_name="knowledge.md",
        existing_project_titles=("Передача диалога менеджеру",),
        groups=(
            KnowledgeSemanticMergeGroup(
                group_id="manager_handoff",
                candidates=(
                    KnowledgeSemanticMergeCandidate(
                        candidate_id="entry-a",
                        title="Передача менеджеру",
                        answer="Ассистент передаёт вопрос менеджеру.",
                        embedding_text="передача менеджеру handoff",
                    ),
                    KnowledgeSemanticMergeCandidate(
                        candidate_id="entry-b",
                        title="Запрос на человека",
                        answer="Клиент может попросить человека.",
                        embedding_text="запрос на человека оператор менеджер",
                    ),
                ),
            ),
        ),
    )

    assert "SEMANTIC MERGE TIGHTENING TASK" in prompt
    assert "suspect duplicate group" in prompt
    assert '"action": "merge | keep_separate"' in prompt
    assert "existing_project_titles" in prompt
    assert "Do not invent facts" in prompt
    assert "Do not merge with existing_project_titles here" in prompt
