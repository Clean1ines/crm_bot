from __future__ import annotations

from collections.abc import Mapping

import asyncio
import json

import pytest

from src.application.rag_eval.dataset_generator import LlmRagEvalDatasetGenerator
from src.application.rag_eval.judge import LlmRagEvalAnswerJudge
from src.application.rag_eval.runner import RagEvalRunner
from src.application.rag_eval.schemas import RagEvalEvidenceEntry, RagEvalQuestion


class FakeJsonLlm:
    async def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
    ) -> Mapping[str, object]:
        if schema_name == "rag_eval_questions_v2":
            return {
                "questions": [
                    {
                        "question": "Сколько занимает подключение?",
                        "question_type": "direct",
                        "expected_entry_ids": ["chunk_1"],
                        "expected_answer_summary": "Подключение занимает 1 рабочий день.",
                        "should_answer": True,
                        "should_escalate": False,
                        "difficulty": 1,
                        "severity": "medium",
                        "metadata": {
                            "why": "direct evidence retrieval",
                            "fact_id": "connection_time_one_business_day",
                            "fact_summary": "Подключение занимает 1 рабочий день.",
                            "variant_style": "direct",
                        },
                    },
                    {
                        "question": "Можно вернуть деньги после отключения?",
                        "question_type": "unknown",
                        "expected_entry_ids": [],
                        "expected_answer_summary": "В документе нет информации о возврате.",
                        "should_answer": False,
                        "should_escalate": False,
                        "difficulty": 3,
                        "severity": "high",
                        "metadata": {
                            "why": "unsupported adjacent question",
                            "fact_id": "refund_policy_absence",
                            "fact_summary": "В документе нет информации о возврате денег.",
                            "variant_style": "unknown",
                        },
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
    ) -> list[RagEvalEvidenceEntry]:
        return [
            RagEvalEvidenceEntry(
                id="chunk_1",
                content="Подключение занимает 1 рабочий день.",
                score=0.95,
            )
        ]


class ForbiddenAnswerer:
    async def answer(
        self,
        *,
        project_id: str,
        question: str,
        evidence: list[RagEvalEvidenceEntry],
    ) -> str:
        raise AssertionError("answerer must not run in retrieval_eval mode")


class ForbiddenJudge:
    async def judge_answer(
        self,
        *,
        question: RagEvalQuestion,
        retrieved_entries: list[RagEvalEvidenceEntry],
        answer_text: str,
    ):
        raise AssertionError("judge must not run in retrieval_eval mode")


class FakeAnswerer:
    async def answer(
        self,
        *,
        project_id: str,
        question: str,
        evidence: list[RagEvalEvidenceEntry],
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
            RagEvalEvidenceEntry(
                id="chunk_1",
                content="Подключение занимает 1 рабочий день.",
            )
        ],
    )

    assert dataset.status == "ready"
    assert dataset.total_questions == 2
    assert {question.question_type for question in dataset.questions} == {
        "direct",
        "unknown",
    }
    assert dataset.questions[0].expected_entry_ids == ["chunk_1"]


@pytest.mark.asyncio
async def test_runner_defaults_to_deterministic_retrieval_eval_without_answer_llms() -> (
    None
):
    runner = RagEvalRunner(
        retriever=FakeRetriever(),
        answerer=ForbiddenAnswerer(),
        answer_judge=ForbiddenJudge(),
    )

    result = await runner.run_question(
        run_id="run_1",
        project_id="project_1",
        question=RagEvalQuestion(
            id="question_1",
            dataset_id="dataset_1",
            project_id="project_1",
            document_id="document_1",
            question="Сколько занимает подключение?",
            question_type="direct",
            expected_entry_ids=["chunk_1"],
            expected_answer_summary="Подключение занимает 1 рабочий день.",
            should_answer=True,
        ),
    )

    assert result.top1_hit is True
    assert result.top3_hit is True
    assert result.top5_hit is True
    assert result.expected_entry_found is True
    assert result.wrong_entry_top1 is False
    assert result.answer_text == ""
    assert result.score == 1.0
    assert result.judge_json["mode"] == "retrieval_eval"


@pytest.mark.asyncio
async def test_runner_marks_retrieval_miss_as_enrichment_candidate() -> None:
    class MissRetriever:
        async def retrieve(
            self,
            *,
            project_id: str,
            question: str,
            limit: int,
        ) -> list[RagEvalEvidenceEntry]:
            return [RagEvalEvidenceEntry(id="chunk_other", content="Другая тема.")]

    runner = RagEvalRunner(retriever=MissRetriever())

    result = await runner.run_question(
        run_id="run_1",
        project_id="project_1",
        question=RagEvalQuestion(
            id="question_1",
            dataset_id="dataset_1",
            project_id="project_1",
            document_id="document_1",
            question="Как быстро подключают?",
            question_type="paraphrase",
            expected_entry_ids=["chunk_1"],
            expected_answer_summary="Подключение занимает 1 рабочий день.",
            should_answer=True,
        ),
    )

    assert result.top1_hit is False
    assert result.expected_entry_found is False
    assert result.wrong_entry_top1 is True
    assert result.score == 0.0
    assert result.classification is not None
    assert result.classification.type.value == "wrong_entry_top1"
    assert [action.action_type.value for action in result.proposed_actions] == [
        "attach_question_to_entry",
        "rebuild_embedding",
        "rerun_eval",
    ]
    assert result.proposed_actions[0].target_entry_id == "chunk_1"
    assert result.proposed_actions[0].payload["question"] == "Как быстро подключают?"


@pytest.mark.asyncio
async def test_runner_answer_quality_mode_combines_retrieval_metrics_and_llm_judge() -> (
    None
):
    generator = LlmRagEvalDatasetGenerator(llm=FakeJsonLlm())
    dataset = await generator.generate_dataset(
        project_id="00000000-0000-0000-0000-000000000001",
        document_id="00000000-0000-0000-0000-000000000002",
        chunks=[
            RagEvalEvidenceEntry(
                id="chunk_1",
                content="Подключение занимает 1 рабочий день.",
            )
        ],
    )

    runner = RagEvalRunner(
        retriever=FakeRetriever(),
        answerer=FakeAnswerer(),
        answer_judge=LlmRagEvalAnswerJudge(llm=FakeJsonLlm()),
        mode="answer_quality_eval",
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


@pytest.mark.asyncio
async def test_llm_dataset_generator_falls_back_when_question_json_is_malformed() -> (
    None
):
    class BrokenJsonLlm:
        async def complete_json(
            self,
            *,
            system_prompt: str,
            user_prompt: str,
            schema_name: str,
        ) -> Mapping[str, object]:
            raise json.JSONDecodeError(
                "Expecting ',' delimiter",
                '{"questions":[{"question":"broken"}',
                31,
            )

    generator = LlmRagEvalDatasetGenerator(llm=BrokenJsonLlm())

    dataset = await generator.generate_dataset(
        project_id="00000000-0000-0000-0000-000000000001",
        document_id="00000000-0000-0000-0000-000000000002",
        chunks=[
            RagEvalEvidenceEntry(
                id="chunk_1",
                content=(
                    "Ассистент должен передать диалог менеджеру, "
                    "если вопрос связан с оплатой, возвратом или договором."
                ),
                metadata={
                    "title": "Передача менеджеру",
                    "source_excerpt": (
                        "Вопросы про оплату, возврат или договор нужно передать менеджеру."
                    ),
                },
            )
        ],
    )

    assert dataset.status == "ready"
    assert dataset.total_questions == 1
    question = dataset.questions[0]
    assert question.question_type == "direct"
    assert question.expected_entry_ids == ["chunk_1"]
    assert question.should_answer is True
    assert "Передача менеджеру" in question.question
    assert "оплату, возврат или договор" in question.expected_answer_summary
    assert question.metadata["variant_style"] == (
        "deterministic_fallback_after_invalid_llm_json"
    )


@pytest.mark.asyncio
async def test_llm_dataset_generator_runs_batches_in_parallel_and_tracks_json_failures() -> (
    None
):
    class ParallelJsonLlm:
        def __init__(self) -> None:
            self.active = 0
            self.max_active = 0
            self.calls_by_entry: dict[str, int] = {}

        async def complete_json(
            self,
            *,
            system_prompt: str,
            user_prompt: str,
            schema_name: str,
        ) -> Mapping[str, object]:
            entry_id = "chunk_1"
            if "chunk_2" in user_prompt:
                entry_id = "chunk_2"
            if "chunk_3" in user_prompt:
                entry_id = "chunk_3"

            self.calls_by_entry[entry_id] = self.calls_by_entry.get(entry_id, 0) + 1
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            try:
                await asyncio.sleep(0.01)
                if entry_id == "chunk_2" and self.calls_by_entry[entry_id] == 1:
                    raise json.JSONDecodeError(
                        "Expecting ',' delimiter",
                        '{"questions":[{"question":"broken"}',
                        31,
                    )
                return {
                    "questions": [
                        {
                            "question": f"Что проверить для {entry_id}?",
                            "question_type": "direct",
                            "expected_entry_ids": [entry_id],
                            "expected_answer_summary": f"Факт {entry_id}",
                            "should_answer": True,
                            "should_escalate": False,
                            "difficulty": 1,
                            "severity": "medium",
                            "metadata": {
                                "fact_id": f"fact_{entry_id}",
                                "fact_summary": f"Факт {entry_id}",
                                "variant_style": "direct",
                                "source_chunk_ids": [entry_id],
                            },
                        }
                    ]
                }
            finally:
                self.active -= 1

    llm = ParallelJsonLlm()
    generator = LlmRagEvalDatasetGenerator(
        llm=llm,
        max_concurrency=2,
        max_batch_attempts=2,
    )
    progress: list[Mapping[str, object]] = []

    dataset = await generator.generate_dataset(
        project_id="00000000-0000-0000-0000-000000000001",
        document_id="00000000-0000-0000-0000-000000000002",
        chunks=[
            RagEvalEvidenceEntry(id="chunk_1", content="Факт один про тариф."),
            RagEvalEvidenceEntry(id="chunk_2", content="Факт два про оплату."),
            RagEvalEvidenceEntry(id="chunk_3", content="Факт три про SLA."),
        ],
        metrics_callback=lambda item: progress.append(item) or noop_async(),
    )

    assert dataset.status == "ready"
    assert dataset.total_questions == 3
    assert llm.max_active == 2
    assert llm.calls_by_entry["chunk_2"] == 2
    assert dataset.metadata["json_parse_failures"] == 1
    assert dataset.metadata["retry_count"] == 1
    assert progress[-1]["processed_batches"] == 3
    assert progress[-1]["json_parse_failures"] == 1


async def noop_async() -> None:
    return None
