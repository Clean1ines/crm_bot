from __future__ import annotations

import asyncio
import importlib
from datetime import UTC, datetime
from typing import Mapping

import pytest

from src.application.rag_eval.dataset_generator import LlmRagEvalDatasetGenerator
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


class JsonLlmStub:
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
                    "question": "сколько это стоит примерно",
                    "variant_style": "colloquial",
                    "reason": "natural user wording",
                }
            ]
        }


class EntrySourceStub:
    def __init__(self, entries: list[RagEvalEvidenceEntry]) -> None:
        self.entries = entries

    async def load_document_entries(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> list[RagEvalEvidenceEntry]:
        return self.entries


class StreamingGeneratorStub:
    def __init__(self, second_done: asyncio.Event) -> None:
        self._model_name = "llama-3.1-8b-instant"
        self._max_concurrency = 2
        self.second_done = second_done

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
            await asyncio.sleep(0.15)
            self.second_done.set()
        else:
            await asyncio.sleep(0.01)
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
            metadata={"source_chunk_id": entry.id},
        )
        return RagEvalDataset(
            id=new_eval_id("dataset"),
            project_id=project_id,
            document_id=document_id,
            status="ready",
            model_used=self._model_name,
            total_questions=1,
            questions=[question],
            metadata={},
        )


class RetrieverStub:
    def __init__(
        self, first_retrieval: asyncio.Event, second_done: asyncio.Event
    ) -> None:
        self.first_retrieval = first_retrieval
        self.second_done = second_done
        self.retrieval_started_before_second_generation_finished = False

    async def retrieve(
        self,
        *,
        project_id: str,
        question: str,
        limit: int,
    ) -> list[RagEvalEvidenceEntry]:
        if not self.second_done.is_set():
            self.retrieval_started_before_second_generation_finished = True
        self.first_retrieval.set()
        expected_id = "entry_1" if "entry_1" in question else "entry_2"
        return [RagEvalEvidenceEntry(id=expected_id, content="answer")]


class StoreStub:
    def __init__(self) -> None:
        self.saved_datasets: list[RagEvalDataset] = []
        self.results: list[RagEvalResult] = []
        self.runs: list[RagEvalRun] = []
        self.reports: list[RagQualityReport] = []

    async def save_dataset(self, *, dataset: RagEvalDataset) -> None:
        self.saved_datasets.append(dataset)

    async def create_run(self, *, run: RagEvalRun) -> None:
        self.runs.append(run)

    async def save_result(self, *, result: RagEvalResult) -> None:
        self.results.append(result)

    async def save_report(self, *, report: RagQualityReport) -> None:
        self.reports.append(report)

    async def finish_run(self, *, run: RagEvalRun) -> None:
        self.runs.append(run)


class ExplodingAnswerer:
    async def answer(
        self, *, project_id: str, question: str, evidence: list[RagEvalEvidenceEntry]
    ) -> str:
        raise AssertionError("retrieval_eval must not call answerer")


class ExplodingJudge:
    async def judge_answer(
        self,
        *,
        question: RagEvalQuestion,
        retrieved_entries: list[RagEvalEvidenceEntry],
        answer_text: str,
    ):
        raise AssertionError("retrieval_eval must not call judge")


@pytest.mark.parametrize(
    "module_name",
    [
        "src.infrastructure.queue.handlers.rag_eval",
        "src.interfaces.http.rag_eval",
    ],
)
def test_default_question_model_is_fast_llama_not_gpt_oss(
    monkeypatch: pytest.MonkeyPatch, module_name: str
) -> None:
    monkeypatch.delenv("RAG_EVAL_QUESTION_MODEL", raising=False)
    module = importlib.reload(importlib.import_module(module_name))
    assert module.RAG_EVAL_QUESTION_MODEL == "llama-3.1-8b-instant"
    assert module.RAG_EVAL_QUESTION_MODEL != "openai/gpt-oss-120b"


def test_question_prompt_contract_uses_variants_not_atomic_facts() -> None:
    llm = JsonLlmStub()
    generator = LlmRagEvalDatasetGenerator(llm=llm)
    entry = RagEvalEvidenceEntry(
        id="entry_1",
        content="Ассистент отвечает круглосуточно.",
        metadata={
            "title": "График ответов",
            "questions": ["бот работает ночью?"],
            "synonyms": ["24/7"],
            "tags": ["support"],
        },
    )

    prompt = generator._user_prompt(
        project_id="00000000-0000-0000-0000-000000000001",
        document_id="00000000-0000-0000-0000-000000000002",
        chunks=[entry],
        batch_index=1,
        total_batches=1,
    )

    assert "extract every atomic fact" not in generator._system_prompt().lower()
    assert "extract every atomic fact" not in prompt.lower()
    assert "questions" in prompt
    assert "synonyms" in prompt
    assert "non-duplicate" in prompt


@pytest.mark.asyncio
async def test_generated_question_gets_expected_entry_from_backend() -> None:
    llm = JsonLlmStub()
    generator = LlmRagEvalDatasetGenerator(llm=llm)
    dataset = await generator.generate_dataset(
        project_id="00000000-0000-0000-0000-000000000001",
        document_id="00000000-0000-0000-0000-000000000002",
        chunks=[
            RagEvalEvidenceEntry(
                id="entry_1",
                content="Стоимость базового тарифа — 1000 рублей.",
                metadata={
                    "title": "Цена",
                    "questions": ["цена?"],
                    "synonyms": ["стоимость"],
                },
            )
        ],
    )

    assert len(dataset.questions) == 1
    question = dataset.questions[0]
    assert question.expected_entry_ids == ["entry_1"]
    assert question.should_answer is True
    assert question.metadata["source_chunk_id"] == "entry_1"


@pytest.mark.asyncio
async def test_streaming_retrieval_starts_before_all_generation_finishes() -> None:
    second_done = asyncio.Event()
    first_retrieval = asyncio.Event()
    retriever = RetrieverStub(first_retrieval, second_done)
    store = StoreStub()
    entries = [
        RagEvalEvidenceEntry(id="entry_1", content="answer 1"),
        RagEvalEvidenceEntry(id="entry_2", content="answer 2"),
    ]
    runner = RagEvalRunner(retriever=retriever, mode="retrieval_eval")
    service = RagEvalService(
        entry_source=EntrySourceStub(entries),
        dataset_generator=StreamingGeneratorStub(second_done),
        runner=runner,
        store=store,
        run_concurrency=2,
    )

    progress_events: list[Mapping[str, object]] = []

    async def metrics_callback(metrics: Mapping[str, object]) -> None:
        progress_events.append(dict(metrics))

    run, _report = await service.generate_dataset_and_run_streaming_retrieval(
        project_id="00000000-0000-0000-0000-000000000001",
        document_id="00000000-0000-0000-0000-000000000002",
        run_metrics_callback=metrics_callback,
    )

    assert run.status == "completed"
    assert retriever.retrieval_started_before_second_generation_finished is True
    assert len(store.results) == 2
    assert any(
        event.get("active_generation_workers") is not None for event in progress_events
    )
    assert any(
        event.get("active_retrieval_workers") is not None for event in progress_events
    )
    assert any(
        event.get("generated_questions") is not None for event in progress_events
    )
    assert any(
        event.get("processed_questions") is not None for event in progress_events
    )
    assert any(event.get("queued_questions") is not None for event in progress_events)
    assert any(
        event.get("failed_retrieval_count") is not None for event in progress_events
    )


@pytest.mark.asyncio
async def test_retrieval_eval_does_not_invoke_answerer_or_judge() -> None:
    class SingleRetriever:
        async def retrieve(
            self,
            *,
            project_id: str,
            question: str,
            limit: int,
        ) -> list[RagEvalEvidenceEntry]:
            return [RagEvalEvidenceEntry(id="entry_1", content="answer")]

    runner = RagEvalRunner(
        retriever=SingleRetriever(),
        answerer=ExplodingAnswerer(),
        answer_judge=ExplodingJudge(),
        mode="retrieval_eval",
    )
    question = RagEvalQuestion(
        id="question_1",
        dataset_id="dataset_1",
        project_id="00000000-0000-0000-0000-000000000001",
        document_id="00000000-0000-0000-0000-000000000002",
        question="цена?",
        question_type="paraphrase",
        expected_entry_ids=["entry_1"],
        expected_answer_summary="answer",
        should_answer=True,
        created_at=datetime.now(UTC),
    )

    result = await runner.run_question(
        run_id="run_1",
        project_id="00000000-0000-0000-0000-000000000001",
        question=question,
    )

    assert result.answer_text == ""
    assert result.judge_json["mode"] == "retrieval_eval"
