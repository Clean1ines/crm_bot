from __future__ import annotations

from collections.abc import Mapping
from typing import cast

import pytest

from src.application.rag_eval.dataset_generator import LlmRagEvalDatasetGenerator
from src.application.rag_eval.judge import LlmRagEvalAnswerJudge
from src.application.rag_eval.runner import RagEvalRunner
from src.application.rag_eval.schemas import (
    RagEvalEvidenceEntry,
    RagEvalDataset,
    RagEvalQuestion,
    RagEvalResult,
    RagEvalRun,
    RagQualityReport,
)
from src.application.rag_eval.service import RagEvalService


class _StaticQuestionLlm:
    async def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
    ) -> Mapping[str, object]:
        return {
            "questions": [
                {
                    "question": "Есть ли в документе раздел с номером 1?",
                    "question_type": "risky",
                    "expected_entry_ids": ["chunk-1"],
                    "expected_answer_summary": 'Section titled "Назначение продукта" exists.',
                    "should_answer": True,
                    "should_escalate": False,
                    "difficulty": 2,
                    "severity": "low",
                    "metadata": {
                        "fact_id": "section_1_product_purpose",
                        "fact_summary": 'Document contains a section titled "Назначение продукта"',
                        "variant_style": "edge_case",
                        "source_chunk_ids": ["chunk-1"],
                    },
                },
                {
                    "question": "Что делает продукт с намерением пользователя?",
                    "question_type": "direct",
                    "expected_entry_ids": ["chunk-1"],
                    "expected_answer_summary": "Продукт классифицирует намерение пользователя.",
                    "should_answer": True,
                    "should_escalate": False,
                    "difficulty": 1,
                    "severity": "medium",
                    "metadata": {
                        "fact_id": "product_classifies_intent",
                        "fact_summary": "Продукт классифицирует намерение пользователя.",
                        "variant_style": "direct",
                        "source_chunk_ids": ["chunk-1"],
                    },
                },
            ]
        }


@pytest.mark.asyncio
async def test_dataset_generator_rejects_document_structure_questions() -> None:
    generator = LlmRagEvalDatasetGenerator(
        llm=_StaticQuestionLlm(),
        model_name="test-model",
    )

    dataset = await generator.generate_dataset(
        project_id="project-1",
        document_id="document-1",
        chunks=[
            RagEvalEvidenceEntry(
                id="chunk-1",
                content="## 1. Назначение продукта\n\nПродукт классифицирует намерение пользователя.",
                metadata={"title": "Назначение продукта"},
            )
        ],
    )

    assert [question.question for question in dataset.questions] == [
        "Что делает продукт с намерением пользователя?"
    ]


def test_fallback_question_does_not_generate_section_scaffold_prompt() -> None:
    generator = LlmRagEvalDatasetGenerator(
        llm=_StaticQuestionLlm(),
        model_name="test-model",
    )

    question = generator._fallback_question_text(
        RagEvalEvidenceEntry(
            id="chunk-1",
            content="## 1. Назначение продукта\n\nПродукт классифицирует намерение пользователя.",
            metadata={"title": "Назначение продукта"},
        )
    )

    assert "раздел" not in question.lower()
    assert "фрагмент" not in question.lower()
    assert "Назначение продукта" in question


class _CaptureJudgeLlm:
    def __init__(self) -> None:
        self.user_prompt = ""

    async def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
    ) -> Mapping[str, object]:
        self.user_prompt = user_prompt
        return {
            "answer_supported": True,
            "hallucination_risk": "low",
            "missing_important_info": False,
            "client_friendly": True,
            "should_answer_passed": True,
            "notes": "ok",
            "score": 1.0,
        }


@pytest.mark.asyncio
async def test_judge_prompt_uses_json_not_python_repr() -> None:
    llm = _CaptureJudgeLlm()
    judge = LlmRagEvalAnswerJudge(llm=llm)

    await judge.judge_answer(
        question=RagEvalQuestion(
            id="question-1",
            dataset_id="dataset-1",
            project_id="project-1",
            document_id="document-1",
            question="Что делает продукт?",
            question_type="direct",
            expected_entry_ids=["chunk-1"],
            expected_answer_summary="Продукт классифицирует намерение.",
            should_answer=True,
        ),
        retrieved_entries=[
            RagEvalEvidenceEntry(
                id="chunk-1",
                content="Продукт классифицирует намерение.",
            )
        ],
        answer_text="Продукт классифицирует намерение.",
    )

    assert '"question":"Что делает продукт?"' in llm.user_prompt
    assert "'question':" not in llm.user_prompt
    assert "Retrieved evidence JSON:" in llm.user_prompt


class _ChunkSource:
    async def load_document_entries(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> list[RagEvalEvidenceEntry]:
        return [
            RagEvalEvidenceEntry(
                id="chunk-1", content="Продукт классифицирует намерение."
            )
        ]


class _DatasetGenerator:
    async def generate_dataset(
        self,
        *,
        project_id: str,
        document_id: str,
        chunks: list[RagEvalEvidenceEntry],
        progress_callback: object | None = None,
        control_callback: object | None = None,
    ) -> RagEvalDataset:
        question_1 = RagEvalQuestion(
            id="question-1",
            dataset_id="dataset-1",
            project_id=project_id,
            document_id=document_id,
            question="сломай judge",
            question_type="direct",
            expected_entry_ids=["chunk-1"],
            expected_answer_summary="Продукт классифицирует намерение.",
            should_answer=True,
        )
        question_2 = RagEvalQuestion(
            id="question-2",
            dataset_id="dataset-1",
            project_id=project_id,
            document_id=document_id,
            question="нормальный вопрос",
            question_type="direct",
            expected_entry_ids=["chunk-1"],
            expected_answer_summary="Продукт классифицирует намерение.",
            should_answer=True,
        )
        return RagEvalDataset(
            id="dataset-1",
            project_id=project_id,
            document_id=document_id,
            status="ready",
            model_used="test-model",
            total_questions=2,
            questions=[question_1, question_2],
        )


class _Runner:
    async def run_question(
        self,
        *,
        run_id: str,
        project_id: str,
        question: RagEvalQuestion,
    ) -> RagEvalResult:
        if question.id == "question-1":
            raise ValueError("broken judge json")

        return RagEvalResult(
            id="result-2",
            run_id=run_id,
            question_id=question.id,
            question=question,
            retrieved_entries=[],
            answer_text="ok",
            top1_hit=True,
            top3_hit=True,
            top5_hit=True,
            expected_entry_found=True,
            wrong_entry_top1=False,
            answer_supported=True,
            hallucination_risk="low",
            should_answer_passed=True,
            score=1.0,
            notes="ok",
        )

    def failed_result(
        self,
        *,
        run_id: str,
        question: RagEvalQuestion,
        error: BaseException,
        stage: str = "question_execution",
    ) -> RagEvalResult:
        return RagEvalResult(
            id="failed-result-1",
            run_id=run_id,
            question_id=question.id,
            question=question,
            retrieved_entries=[],
            answer_text="",
            top1_hit=False,
            top3_hit=False,
            top5_hit=False,
            expected_entry_found=False,
            wrong_entry_top1=True,
            answer_supported=False,
            hallucination_risk="high",
            should_answer_passed=False,
            score=0.0,
            notes=f"{stage}: {type(error).__name__}",
            judge_json={"error_type": type(error).__name__, "recovered": True},
        )


class _Store:
    def __init__(self) -> None:
        self.results: list[RagEvalResult] = []

    async def save_dataset(self, *, dataset: RagEvalDataset) -> None:
        return None

    async def create_run(self, *, run: RagEvalRun) -> None:
        return None

    async def save_result(self, *, result: RagEvalResult) -> None:
        self.results.append(result)

    async def finish_run(self, *, run: RagEvalRun) -> None:
        return None

    async def save_report(self, *, report: RagQualityReport) -> None:
        return None


@pytest.mark.asyncio
async def test_service_records_failed_question_and_continues_run() -> None:
    store = _Store()
    service = RagEvalService(
        entry_source=_ChunkSource(),
        dataset_generator=_DatasetGenerator(),
        runner=cast(RagEvalRunner, _Runner()),
        store=store,
    )

    run, report = await service.generate_dataset_and_run(
        project_id="project-1",
        document_id="document-1",
    )

    assert run.status == "completed"
    assert len(run.results) == 2
    assert len(store.results) == 2
    assert run.results[0].score == 0.0
    assert run.results[0].judge_json["recovered"] is True
    assert run.results[1].score == 1.0
    assert report.metrics["total"] == 2


class _RetrieverForTechnicalAnswer:
    async def retrieve(
        self,
        *,
        project_id: str,
        question: str,
        limit: int,
    ) -> list[RagEvalEvidenceEntry]:
        return [
            RagEvalEvidenceEntry(
                id="chunk-1", content="Продукт классифицирует намерение."
            )
        ]


class _TechnicalAnswerer:
    async def answer(
        self,
        *,
        project_id: str,
        question: str,
        evidence: list[RagEvalEvidenceEntry],
    ) -> str:
        return (
            "Не получилось сгенерировать ответ из-за технической ошибки. "
            "Можете повторить запрос, а если вопрос срочный — я передам диалог менеджеру."
        )


class _JudgeMustNotRun:
    async def judge_answer(
        self,
        *,
        question: RagEvalQuestion,
        retrieved_entries: list[RagEvalEvidenceEntry],
        answer_text: str,
    ):
        raise AssertionError("judge must not run for technical fallback answers")


@pytest.mark.asyncio
async def test_runner_rejects_technical_answer_fallback_before_judge() -> None:
    from src.application.rag_eval.runner import (
        RagEvalRunner,
        RagEvalTechnicalAnswerError,
    )

    runner = RagEvalRunner(
        retriever=_RetrieverForTechnicalAnswer(),
        answerer=_TechnicalAnswerer(),
        answer_judge=_JudgeMustNotRun(),
        mode="answer_quality_eval",
    )

    with pytest.raises(RagEvalTechnicalAnswerError):
        await runner.run_question(
            run_id="run-1",
            project_id="project-1",
            question=RagEvalQuestion(
                id="question-technical",
                dataset_id="dataset-1",
                project_id="project-1",
                document_id="document-1",
                question="Что делает продукт?",
                question_type="direct",
                expected_entry_ids=["chunk-1"],
                expected_answer_summary="Продукт классифицирует намерение.",
                should_answer=True,
            ),
        )


def test_document_structure_question_guard_rejects_real_bad_shapes() -> None:
    from src.application.rag_eval.dataset_generator import (
        is_document_structure_eval_question,
    )

    bad_questions = [
        "Что сказано в разделе «1. Назначение продукта»?",
        "Есть ли в документе раздел с номером 1?",
        "О чём речь в первой части?",
        "В каком разделе указано, кто является целевой аудиторией продукта?",
        "Где указано, что продукт подходит агентствам?",
        "Что написано в разделе «30. Правила ответа ассистента»?",
    ]

    for question in bad_questions:
        assert is_document_structure_eval_question(question), question


def test_document_structure_question_guard_allows_real_client_questions() -> None:
    from src.application.rag_eval.dataset_generator import (
        is_document_structure_eval_question,
    )

    good_questions = [
        "Что делает AI-ассистент с клиентскими обращениями?",
        "Можно ли передать диалог менеджеру?",
        "Сохраняется ли история переписки?",
        "Если вопрос связан с возвратом денег, что должен сделать ассистент?",
        "Можно ли использовать продукт для нескольких проектов?",
        "Сколько стоит внедрение ассистента?",
    ]

    for question in good_questions:
        assert not is_document_structure_eval_question(question), question
