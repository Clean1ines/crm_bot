from __future__ import annotations

from collections.abc import Mapping

import pytest

from src.application.rag_eval.dataset_generator import LlmRagEvalDatasetGenerator
from src.application.rag_eval.schemas import RagEvalChunk


class _PromptCapturingLlm:
    def __init__(self) -> None:
        self.user_prompts: list[str] = []

    async def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
    ) -> Mapping[str, object]:
        self.user_prompts.append(user_prompt)
        if schema_name != "rag_eval_questions_v2":
            raise AssertionError(schema_name)

        if '"id":"chunk-a"' not in user_prompt:
            return {"questions": []}

        return {
            "questions": [
                {
                    "question": "Что делает CRM Bot с обращениями клиентов?",
                    "question_type": "direct",
                    "expected_chunk_ids": ["chunk-a"],
                    "expected_answer_summary": (
                        "CRM Bot принимает обращения клиентов и классифицирует "
                        "их намерение."
                    ),
                    "should_answer": True,
                    "should_escalate": False,
                    "difficulty": 1,
                    "severity": "medium",
                    "metadata": {
                        "fact_id": "crm_bot_handles_and_classifies_requests",
                        "fact_summary": (
                            "CRM Bot принимает обращения клиентов и "
                            "классифицирует их намерение."
                        ),
                        "variant_style": "direct",
                        "source_chunk_ids": ["chunk-a"],
                    },
                }
            ]
        }


@pytest.mark.asyncio
async def test_dataset_generator_builds_canonical_eval_units_and_expands_expected_ids() -> (
    None
):
    llm = _PromptCapturingLlm()
    generator = LlmRagEvalDatasetGenerator(llm=llm, model_name="test-model")

    dataset = await generator.generate_dataset(
        project_id="project-1",
        document_id="document-1",
        chunks=[
            RagEvalChunk(
                id="chunk-a",
                content="## 1. Назначение продукта CRM Bot принимает обращения клиентов.",
                metadata={
                    "entry_type": "answer_knowledge",
                    "title": "1. Назначение продукта",
                },
            ),
            RagEvalChunk(
                id="chunk-b",
                content=(
                    "CRM Bot принимает обращения клиентов и классифицирует "
                    "намерение клиента перед ответом."
                ),
                metadata={
                    "entry_type": "answer_knowledge",
                    "title": "1. Назначение продукта",
                },
            ),
            RagEvalChunk(
                id="faq-1",
                content="Клиент может спросить о сроках подключения продукта.",
                metadata={
                    "entry_type": "faq",
                    "title": "Сроки подключения",
                },
            ),
            RagEvalChunk(
                id="price-1",
                content="Стоимость внедрения зависит от количества проектов.",
                metadata={
                    "entry_type": "price_list",
                    "title": "Стоимость",
                },
            ),
            RagEvalChunk(
                id="eval-test-1",
                content="НЕ ДОЛЖНО ПОПАСТЬ В PROMPT: встроенный тест.",
                metadata={
                    "entry_type": "internal_eval_test",
                    "title": "Тесты",
                },
            ),
            RagEvalChunk(
                id="guideline-1",
                content="НЕ ДОЛЖНО ПОПАСТЬ В PROMPT: правило поиска.",
                metadata={
                    "entry_type": "retrieval_guideline",
                    "title": "Правила поиска",
                },
            ),
            RagEvalChunk(
                id="negative-1",
                content="НЕ ДОЛЖНО ПОПАСТЬ В PROMPT: негативная проверка.",
                metadata={
                    "entry_type": "negative_test",
                    "title": "Негативные тесты",
                },
            ),
            RagEvalChunk(
                id="empty-section",
                content="## 9. Пустой раздел\n\n---",
                metadata={
                    "entry_type": "answer_knowledge",
                    "title": "9. Пустой раздел",
                },
            ),
            RagEvalChunk(
                id="",
                content="У этого chunk нет id, его нельзя использовать как source.",
                metadata={
                    "entry_type": "answer_knowledge",
                    "title": "Без id",
                },
            ),
        ],
    )

    assert len(llm.user_prompts) == 3
    joined_prompts = "\n".join(llm.user_prompts)
    assert (
        "CRM Bot принимает обращения клиентов и классифицирует "
        "намерение клиента перед ответом."
    ) in llm.user_prompts[0]
    assert "CRM Bot принимает обращения клиентов." not in llm.user_prompts[0]
    assert "1. Назначение продукта CRM Bot" not in llm.user_prompts[0]
    assert "НЕ ДОЛЖНО ПОПАСТЬ В PROMPT" not in joined_prompts
    assert "Пустой раздел" not in joined_prompts
    assert "нет id" not in joined_prompts

    assert dataset.status == "ready"
    assert dataset.metadata["source_chunk_count"] == 9
    assert dataset.metadata["canonical_eval_unit_count"] == 3
    assert dataset.metadata["useful_chunk_count"] == 3

    assert dataset.total_questions == 1
    question = dataset.questions[0]
    assert question.expected_chunk_ids == ["chunk-a", "chunk-b"]
    assert question.metadata["source_chunk_ids"] == ["chunk-a", "chunk-b"]


@pytest.mark.asyncio
async def test_dataset_generator_fallback_expands_expected_ids_for_same_title_fragments() -> (
    None
):
    class _BrokenJsonLlm:
        async def complete_json(
            self,
            *,
            system_prompt: str,
            user_prompt: str,
            schema_name: str,
        ) -> Mapping[str, object]:
            raise ValueError("invalid json")

    generator = LlmRagEvalDatasetGenerator(llm=_BrokenJsonLlm())

    dataset = await generator.generate_dataset(
        project_id="project-1",
        document_id="document-1",
        chunks=[
            RagEvalChunk(
                id="chunk-a",
                content="CRM Bot принимает обращения клиентов.",
                metadata={
                    "entry_type": "answer_knowledge",
                    "title": "1. Назначение продукта",
                },
            ),
            RagEvalChunk(
                id="chunk-b",
                content="CRM Bot классифицирует намерение клиента.",
                metadata={
                    "entry_type": "answer_knowledge",
                    "title": "1. Назначение продукта",
                },
            ),
        ],
    )

    assert dataset.status == "ready"
    assert dataset.total_questions == 1
    assert dataset.questions[0].expected_chunk_ids == ["chunk-a", "chunk-b"]
    assert dataset.questions[0].metadata["source_chunk_ids"] == ["chunk-a", "chunk-b"]
