from __future__ import annotations

import asyncio
from collections.abc import Mapping
from time import perf_counter

import pytest

from src.application.rag_eval.dataset_generator import LlmRagEvalDatasetGenerator
from src.application.rag_eval.reporter import RagQualityReporter
from src.application.rag_eval.runner import RagEvalRunner
from src.application.rag_eval.schemas import (
    RagEvalDataset,
    RagEvalEvidenceEntry,
    RagEvalQuestion,
    RagEvalResult,
    RagEvalRun,
    RagQualityReport,
    new_eval_id,
)
from src.application.rag_eval.service import RagEvalService


class CapturingJsonLlm:
    def __init__(self) -> None:
        self.system_prompt = ""
        self.user_prompt = ""

    async def complete_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        schema_name: str,
    ) -> Mapping[str, object]:
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt
        return {
            "questions": [
                {
                    "question": "можно написать поздно вечером?",
                    "variant_style": "colloquial",
                    "reason": "natural customer wording",
                }
            ]
        }


@pytest.mark.asyncio
async def test_question_prompt_contract_is_retrieval_only_entry_variants() -> None:
    llm = CapturingJsonLlm()
    generator = LlmRagEvalDatasetGenerator(llm=llm)
    entry = RagEvalEvidenceEntry(
        id="entry_1",
        content="Ассистент отвечает клиентам круглосуточно.",
        metadata={
            "title": "График ответов",
            "questions": ["работаете ночью?"],
            "synonyms": ["24/7"],
            "tags": ["support"],
        },
    )

    await generator.generate_dataset(
        project_id="project_1",
        document_id="doc_1",
        chunks=[entry],
    )

    prompt = f"{llm.system_prompt}\n{llm.user_prompt}".lower()
    assert "extract every atomic fact" not in prompt
    assert "existing_questions" in prompt
    assert "existing_synonyms" in prompt
    assert "non-duplicate user question variants" in prompt
    assert "atomic" in prompt


def test_generated_question_gets_expected_entry_id_from_source_entry() -> None:
    generator = LlmRagEvalDatasetGenerator(llm=CapturingJsonLlm())
    entry = RagEvalEvidenceEntry(
        id="entry_1",
        content="Ассистент отвечает клиентам круглосуточно.",
        metadata={"questions": ["работаете ночью?"], "synonyms": ["24/7"]},
    )

    result = generator._batch_result_from_response(
        dataset_id="dataset_1",
        project_id="project_1",
        document_id="doc_1",
        batch_index=1,
        response={
            "questions": [
                {
                    "question": "можно написать поздно вечером?",
                    "variant_style": "colloquial",
                    "reason": "natural customer wording",
                }
            ]
        },
        valid_entry_ids={"entry_1"},
        related_entry_ids_by_id={"entry_1": ["entry_1"]},
        source_entries_by_id={"entry_1": entry},
        json_parse_failures=0,
        provider_failures=0,
        retry_count=0,
    )

    assert len(result.questions) == 1
    question = result.questions[0]
    assert question.expected_entry_ids == ["entry_1"]
    assert question.should_answer is True
    assert question.metadata["source_chunk_id"] == "entry_1"
    assert question.metadata["expected_entry_id"] == "entry_1"


class FakeEntrySource:
    async def load_document_entries(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> list[RagEvalEvidenceEntry]:
        return [
            RagEvalEvidenceEntry(id="entry_1", content="Первый ответ"),
            RagEvalEvidenceEntry(id="entry_2", content="Второй ответ"),
        ]


class DelayedQuestionGenerator:
    _max_concurrency = 2
    _model_name = "test_question_model"

    def __init__(self, events: list[tuple[str, str, float]]) -> None:
        self.events = events

    async def generate_dataset(
        self,
        *,
        project_id: str,
        document_id: str,
        chunks: list[RagEvalEvidenceEntry],
        progress_callback=None,
        control_callback=None,
        metrics_callback=None,
    ) -> RagEvalDataset:
        entry = chunks[0]
        if entry.id == "entry_2":
            await asyncio.sleep(0.05)

        question = RagEvalQuestion(
            id=new_eval_id("question"),
            dataset_id="temporary_dataset",
            project_id=project_id,
            document_id=document_id,
            question=f"question for {entry.id}",
            question_type="paraphrase",
            expected_entry_ids=[entry.id],
            expected_answer_summary=entry.content,
            should_answer=True,
            metadata={
                "source_chunk_id": entry.id,
                "expected_entry_id": entry.id,
            },
        )
        self.events.append(("generated", entry.id, perf_counter()))
        return RagEvalDataset(
            id=new_eval_id("dataset"),
            project_id=project_id,
            document_id=document_id,
            status="ready",
            model_used="test_question_model",
            total_questions=1,
            questions=[question],
        )


class FakeRetriever:
    async def retrieve(
        self,
        *,
        project_id: str,
        question: str,
        limit: int,
    ) -> list[RagEvalEvidenceEntry]:
        entry_id = "entry_1" if "entry_1" in question else "entry_2"
        return [RagEvalEvidenceEntry(id=entry_id, content=f"answer for {entry_id}")]


class FakeStore:
    def __init__(self, events: list[tuple[str, str, float]] | None = None) -> None:
        self.events = events if events is not None else []
        self.saved_datasets: list[RagEvalDataset] = []
        self.saved_questions: list[RagEvalQuestion] = []
        self.saved_results: list[RagEvalResult] = []
        self.finished_runs: list[RagEvalRun] = []
        self.saved_reports: list[RagQualityReport] = []

    async def save_dataset(self, *, dataset: RagEvalDataset) -> None:
        self.saved_datasets.append(dataset)
        self.saved_questions = list(dataset.questions)

    async def save_questions(self, *, questions: list[RagEvalQuestion]) -> None:
        self.saved_questions.extend(questions)

    async def create_run(self, *, run: RagEvalRun) -> None:
        return None

    async def save_result(self, *, result: RagEvalResult) -> None:
        self.saved_results.append(result)
        self.events.append(
            ("retrieved", result.question.expected_entry_ids[0], perf_counter())
        )

    async def finish_run(self, *, run: RagEvalRun) -> None:
        self.finished_runs.append(run)

    async def save_report(self, *, report: RagQualityReport) -> None:
        self.saved_reports.append(report)

    async def upsert_review_group(
        self,
        *,
        run_id: str,
        dataset_id: str,
        project_id: str,
        document_id: str,
        source_chunk_id: str,
        status: str,
        questions_total: int = 0,
        checked_questions: int = 0,
        reliable_count: int = 0,
        weak_count: int = 0,
        confused_count: int = 0,
        missing_count: int = 0,
        improvement_count: int = 0,
        review_payload: Mapping[str, object] | None = None,
        error: str = "",
    ) -> None:
        return None


@pytest.mark.asyncio
async def test_streaming_retrieval_starts_before_all_entries_finish_generation() -> (
    None
):
    events: list[tuple[str, str, float]] = []
    progress_payloads: list[Mapping[str, object]] = []
    store = FakeStore(events)

    service = RagEvalService(
        entry_source=FakeEntrySource(),
        dataset_generator=DelayedQuestionGenerator(events),
        runner=RagEvalRunner(
            retriever=FakeRetriever(),
            mode="retrieval_eval",
            retrieval_limit=5,
        ),
        reporter=RagQualityReporter(),
        store=store,
        run_concurrency=2,
    )

    async def on_metrics(payload: Mapping[str, object]) -> None:
        progress_payloads.append(dict(payload))

    await service.generate_dataset_and_run_streaming_retrieval(
        project_id="00000000-0000-0000-0000-000000000001",
        document_id="00000000-0000-0000-0000-000000000002",
        run_metrics_callback=on_metrics,
    )

    generated_entry_2_at = next(
        ts
        for event, entry_id, ts in events
        if event == "generated" and entry_id == "entry_2"
    )
    retrieved_entry_1_at = next(
        ts
        for event, entry_id, ts in events
        if event == "retrieved" and entry_id == "entry_1"
    )

    assert retrieved_entry_1_at < generated_entry_2_at
    assert len(store.saved_questions) == 2
    assert len(store.saved_results) == 2
    assert any(
        payload.get("stage") == "fragment_review_streaming"
        for payload in progress_payloads
    )

    latest = progress_payloads[-1]
    for key in {
        "active_generation_workers",
        "active_retrieval_workers",
        "generated_questions",
        "processed_questions",
        "queued_questions",
        "failed_retrieval_count",
    }:
        assert key in latest


class ExplodingAnswerer:
    async def answer(
        self,
        *,
        project_id: str,
        question: str,
        evidence: list[RagEvalEvidenceEntry],
    ) -> str:
        raise AssertionError("answerer must not be called in retrieval_eval")


class ExplodingJudge:
    async def judge_answer(
        self,
        *,
        question: RagEvalQuestion,
        retrieved_entries: list[RagEvalEvidenceEntry],
        answer_text: str,
    ):
        raise AssertionError("judge must not be called in retrieval_eval")


@pytest.mark.asyncio
async def test_retrieval_eval_does_not_invoke_answerer_or_judge() -> None:
    runner = RagEvalRunner(
        retriever=FakeRetriever(),
        answerer=ExplodingAnswerer(),
        answer_judge=ExplodingJudge(),
        mode="retrieval_eval",
        retrieval_limit=5,
    )
    question = RagEvalQuestion(
        id="question_1",
        dataset_id="dataset_1",
        project_id="project_1",
        document_id="doc_1",
        question="question for entry_1",
        question_type="paraphrase",
        expected_entry_ids=["entry_1"],
        expected_answer_summary="answer",
        should_answer=True,
    )

    result = await runner.run_question(
        run_id="run_1",
        project_id="project_1",
        question=question,
    )

    assert result.answer_text == ""
    assert result.judge_json["mode"] == "retrieval_eval"
    assert result.top1_hit is True
