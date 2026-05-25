from __future__ import annotations

import json
from src.infrastructure.llm.knowledge_preprocessor import GroqKnowledgePreprocessor


def _preprocessor() -> GroqKnowledgePreprocessor:
    preprocessor = GroqKnowledgePreprocessor.__new__(GroqKnowledgePreprocessor)
    preprocessor._max_chunks = 1
    preprocessor._max_chunk_chars = 900
    return preprocessor


def test_extractor_prompt_omits_known_intents_from_source_payload() -> None:
    prompt = _preprocessor()._build_prompt(
        mode="faq",
        chunks=[{"content": "Refund policy: manager checks the order."}],
        file_name="faq.txt",
    )

    payload = json.loads(
        prompt.rsplit("ОБРАБОТАЙ SOURCE JSON НИЖЕ. ВЕРНИ ТОЛЬКО JSON:", 1)[1]
    )

    assert "known_question_intents" not in prompt
    assert "previous_answer_titles" not in payload
    assert "previous_entry_titles" not in payload
    assert payload == {
        "file_name": "faq.txt",
        "mode": "faq",
        "chunks": [{"index": 0, "content": "Refund policy: manager checks the order."}],
    }


def test_faq_prompt_requires_split_replacement_answer_and_compact_embedding_text() -> (
    None
):
    prompt = _preprocessor()._build_prompt(
        mode="faq",
        chunks=[{"content": "Цена: 100. Подключение: заявка менеджеру."}],
        file_name="faq.txt",
    )

    assert "Один fragment отвечает на один конкретный клиентский вопрос" in prompt
    assert "Один chunk может дать несколько fragments" in prompt
    assert "Не объединяй результат с предыдущими ответами" in prompt
    assert "Не возвращай match, kind, known_intent_id" in prompt
    assert "answer_fragment" in prompt


def test_markdown_semantic_section_is_not_silently_truncated_to_900_chars() -> None:
    long_section = "A" * 1300
    long_excerpt = "B" * 1400
    long_child_body = "C" * 1250
    prompt = _preprocessor()._build_prompt(
        mode="faq",
        chunks=[
            {
                "content": long_section,
                "section_title": "Long section",
                "section_body": long_section,
                "source_excerpt": long_excerpt,
                "children": [
                    {"title": "Child 1", "body": long_child_body, "source_excerpt": long_child_body}
                ],
            }
        ],
        file_name="faq.md",
    )

    payload = json.loads(
        prompt.rsplit("ОБРАБОТАЙ SOURCE JSON НИЖЕ. ВЕРНИ ТОЛЬКО JSON:", 1)[1]
    )
    chunk = payload["chunks"][0]
    assert len(chunk["content"]) == 1300
    assert len(chunk["section_body"]) == 1300
    assert len(chunk["source_excerpt"]) == 1400
    assert len(chunk["children"][0]["body"]) == 1250
