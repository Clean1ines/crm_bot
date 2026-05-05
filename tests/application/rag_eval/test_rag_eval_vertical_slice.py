from __future__ import annotations

from collections.abc import Mapping

import pytest

from src.application.rag_eval.dataset_generator import LlmRagEvalDatasetGenerator
from src.application.rag_eval.judge import LlmRagEvalAnswerJudge
from src.application.rag_eval.runner import RagEvalRunner
from src.application.rag_eval.schemas import RagEvalChunk


class FakeJsonLlm:
    async def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
    ) -> Mapping[str, object]:
        if schema_name == "rag_eval_questions_v1":
            return {
                "questions": [
                    {
                        "question": "Сколько занимает подключение?",
                        "question_type": "direct",
                        "expected_chunk_ids": ["chunk_1"],
                        "expected_answer_summary": "Подключение занимает 1 рабочий день.",
                        "should_answer": True,
                        "should_escalate": False,
                        "difficulty": 1,
                        "severity": "medium",
                        "metadata": {"why": "direct evidence retrieval"},
                    },
                    {
                        "question": "Можно вернуть деньги после отключения?",
                        "question_type": "unknown",
                        "expected_chunk_ids": [],
                        "expected_answer_summary": "В документе нет информации о возврате.",
                        "should_answer": False,
                        "should_escalate": False,
                        "difficulty": 3,
                        "severity": "high",
                        "metadata": {"why": "unsupported adjacent question"},
                    },
                ]
            }

        if schema_name == "rag_eval_answer_judge_v1":
            if "вернуть деньги" in user_prompt:
                return {
                    "answer_supported": False,
                    "hallucination_risk": "high",
                    "missing_important_info": False,
                    "client_friendly": True,
                    "should_answer_passed": False,
                    "notes": "Answer invents refund information.",
                    "score": 0.1,
                }

            return {
                "answer_supported": True,
                "hallucination_risk": "low",
                "missing_important_info": False,
                "client_friendly": True,
                "should_answer_passed": True,
                "notes": "Answer is supported by expected evidence.",
                "score": 1.0,
            }

        raise AssertionError(schema_name)


class FakeRetriever:
    async def retrieve(
        self,
        *,
        project_id: str,
        question: str,
        limit: int,
    ) -> list[RagEvalChunk]:
        return [
            RagEvalChunk(
                id="chunk_1",
                content="Подключение занимает 1 рабочий день.",
                score=0.95,
            )
        ]


class FakeAnswerer:
    async def answer(
        self,
        *,
        project_id: str,
        question: str,
        evidence: list[RagEvalChunk],
    ) -> str:
        if "вернуть деньги" in question:
            return "Да, возврат денег возможен после отключения."
        return "Подключение занимает 1 рабочий день."


@pytest.mark.asyncio
async def test_llm_dataset_generator_creates_eval_artifact_without_topic_hardcode() -> (
    None
):
    generator = LlmRagEvalDatasetGenerator(llm=FakeJsonLlm())
    dataset = await generator.generate_dataset(
        project_id="00000000-0000-0000-0000-000000000001",
        document_id="00000000-0000-0000-0000-000000000002",
        chunks=[
            RagEvalChunk(
                id="chunk_1",
                content="Подключение занимает 1 рабочий день.",
            )
        ],
        max_questions=10,
    )

    assert dataset.status == "ready"
    assert dataset.total_questions == 2
    assert {question.question_type for question in dataset.questions} == {
        "direct",
        "unknown",
    }
    assert dataset.questions[0].expected_chunk_ids == ["chunk_1"]


@pytest.mark.asyncio
async def test_runner_combines_retrieval_metrics_and_llm_judge() -> None:
    generator = LlmRagEvalDatasetGenerator(llm=FakeJsonLlm())
    dataset = await generator.generate_dataset(
        project_id="00000000-0000-0000-0000-000000000001",
        document_id="00000000-0000-0000-0000-000000000002",
        chunks=[
            RagEvalChunk(
                id="chunk_1",
                content="Подключение занимает 1 рабочий день.",
            )
        ],
        max_questions=10,
    )

    runner = RagEvalRunner(
        retriever=FakeRetriever(),
        answerer=FakeAnswerer(),
        answer_judge=LlmRagEvalAnswerJudge(llm=FakeJsonLlm()),
    )

    direct_result = await runner.run_question(
        run_id="run_1",
        project_id=dataset.project_id,
        question=dataset.questions[0],
    )
    unknown_result = await runner.run_question(
        run_id="run_1",
        project_id=dataset.project_id,
        question=dataset.questions[1],
    )

    assert direct_result.top1_hit is True
    assert direct_result.answer_supported is True
    assert direct_result.score > 0.9

    assert unknown_result.question.question_type == "unknown"
    assert unknown_result.answer_supported is False
    assert unknown_result.hallucination_risk == "high"
    assert unknown_result.score < 0.5
