from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from time import perf_counter
from typing import cast


from src.application.rag_eval.failure_classification import (
    KnowledgeEditAction,
    KnowledgeEditActionType,
)
from src.application.rag_eval.reporter import RagQualityReporter
from src.application.rag_eval.review_service import (
    RagEvalReviewService,
    build_review_payload,
)
from src.application.rag_eval.runner import RagEvalRunner
from src.application.rag_eval.schemas import (
    RagEvalDataset,
    RagEvalEvidenceEntry,
    RagEvalQuestion,
    RagEvalQuestionType,
    RagEvalResult,
    new_eval_id,
)
from src.application.rag_eval.service import RagEvalService


def _question(
    question_id: str,
    *,
    entry_id: str,
    question: str,
    question_type: str = "paraphrase",
) -> RagEvalQuestion:
    return RagEvalQuestion(
        id=question_id,
        dataset_id="dataset_1",
        project_id="00000000-0000-0000-0000-000000000001",
        document_id="00000000-0000-0000-0000-000000000002",
        question=question,
        question_type=cast(RagEvalQuestionType, question_type),
        expected_entry_ids=[entry_id],
        expected_answer_summary="answer",
        should_answer=True,
        metadata={"source_chunk_id": entry_id},
    )


def _result(
    result_id: str,
    question: RagEvalQuestion,
    *,
    retrieved_ids: list[str],
    top1_hit: bool = False,
    expected_found: bool = False,
    wrong_top1: bool = False,
    actions: list[KnowledgeEditAction] | None = None,
) -> RagEvalResult:
    return RagEvalResult(
        id=result_id,
        run_id="run_1",
        question_id=question.id,
        question=question,
        retrieved_entries=[],
        answer_text="",
        top1_hit=top1_hit,
        top3_hit=expected_found,
        top5_hit=expected_found,
        expected_entry_found=expected_found,
        wrong_entry_top1=wrong_top1,
        answer_supported=True,
        hallucination_risk="low",
        should_answer_passed=True,
        score=1.0 if top1_hit else 0.4,
        proposed_actions=actions or [],
        judge_json={"retrieved_entry_ids": retrieved_ids},
    )


def test_review_payload_groups_questions_by_expected_entry_and_problem_map() -> None:
    price_entry = RagEvalEvidenceEntry(
        id="entry_price",
        content="Стоимость зависит от конфигурации.",
        metadata={"title": "Стоимость", "questions": ["Сколько стоит?"]},
    )
    refund_entry = RagEvalEvidenceEntry(
        id="entry_refund",
        content="Возврат возможен в течение недели.",
        metadata={"title": "Возврат"},
    )
    good_question = _question(
        "q_good", entry_id="entry_price", question="Сколько стоит ассистент?"
    )
    bad_question = _question(
        "q_bad",
        entry_id="entry_price",
        question="сколька стоить?",
        question_type="short_vague",
    )
    action = KnowledgeEditAction(
        action_type=KnowledgeEditActionType.ATTACH_QUESTION_TO_ENTRY,
        target_entry_id="entry_price",
        reason="Improve retrieval.",
        payload={"question": bad_question.question},
    )

    payload = build_review_payload(
        run={
            "id": "run_1",
            "dataset_id": "dataset_1",
            "project_id": "00000000-0000-0000-0000-000000000001",
            "document_id": "00000000-0000-0000-0000-000000000002",
            "status": "completed",
            "retriever_version": "production_rag",
            "reranker_version": "production_rag",
            "generator_model": "test-model",
        },
        entries=[price_entry, refund_entry],
        results=[
            _result(
                "r_good",
                good_question,
                retrieved_ids=["entry_price"],
                top1_hit=True,
                expected_found=True,
            ),
            _result(
                "r_bad",
                bad_question,
                retrieved_ids=["entry_refund"],
                wrong_top1=True,
                actions=[action],
            ),
        ],
        reviews={},
    )

    assert payload["summary"]["questions_total"] == 2
    assert payload["summary"]["problem_questions"] == 1
    assert payload["summary"]["readiness"] == "Проблемная база"
    assert payload["groups"][0]["entry_id"] == "entry_price"
    assert payload["groups"][0]["question_count"] == 2
    assert payload["groups"][0]["problem_count"] == 1
    assert payload["groups"][0]["existing_questions"] == ["Сколько стоит?"]
    assert payload["groups"][0]["questions"][1]["review"] == {"status": "candidate"}
    assert payload["problem_map"]["problem_types"] == [
        {"type": "short_vague", "label": "короткий/vague вопрос", "count": 1}
    ]


class _ReviewRepo:
    def __init__(self) -> None:
        self.marked: list[str] = []

    async def get_run_summary(self, *, run_id: str):
        return {
            "id": run_id,
            "dataset_id": "dataset_1",
            "project_id": "00000000-0000-0000-0000-000000000001",
            "document_id": "00000000-0000-0000-0000-000000000002",
            "status": "completed",
            "started_at": datetime.now(UTC).isoformat(),
            "finished_at": datetime.now(UTC).isoformat(),
            "retriever_version": "production_rag",
            "reranker_version": "production_rag",
            "generator_model": "test-model",
            "result_count": 1,
        }

    async def load_accepted_question_reviews(self, *, run_id: str):
        return [
            {
                "review_id": "review_accepted",
                "question_id": "q_accepted",
                "result_id": "r_accepted",
                "document_id": "00000000-0000-0000-0000-000000000002",
                "target_entry_id": "00000000-0000-0000-0000-000000000003",
                "question": "Сколько стоит?",
            }
        ]

    async def mark_question_reviews_applied(
        self, *, review_ids: list[str], reviewed_by: str
    ) -> None:
        self.marked.extend(review_ids)


class _KnowledgeRepo:
    def __init__(self) -> None:
        self.attached: list[str] = []
        self.rebuilt: list[str] = []
        self.actions: list[dict[str, object]] = []

    async def create_or_get_knowledge_edit_action(self, **kwargs):
        self.actions.append(dict(kwargs))
        return {"id": kwargs["action_id"], "status": "proposed"}

    async def attach_question_to_entry(self, **kwargs) -> None:
        self.attached.append(str(kwargs["question"]))

    async def rebuild_entry_embedding(self, **kwargs) -> None:
        self.rebuilt.append(str(kwargs["target_entry_id"]))

    async def mark_knowledge_edit_action_applied(
        self, action_id: str, *, result_payload=None
    ) -> None:
        return None


class _QueueRepo:
    def __init__(self) -> None:
        self.enqueued: list[dict[str, object]] = []

    async def enqueue(self, task_type: str, payload=None, max_attempts: int = 3) -> str:
        self.enqueued.append(
            {
                "task_type": task_type,
                "payload": payload or {},
                "max_attempts": max_attempts,
            }
        )
        return "job_1"


def test_apply_accepted_questions_uses_audit_flow_and_marks_applied() -> None:
    async def run_test() -> None:
        review_repo = _ReviewRepo()
        knowledge_repo = _KnowledgeRepo()
        queue_repo = _QueueRepo()
        service = RagEvalReviewService(
            review_repo,
            knowledge_repo=knowledge_repo,
            queue_repo=queue_repo,
            rerun_eval_task_type="run_full_rag_eval",
        )

        summary = await service.apply_accepted_questions(
            run_id="run_1",
            actor_user_id="user_1",
        )

        assert summary["applied_questions"] == 1
        assert summary["failed_questions"] == 0
        assert knowledge_repo.attached == ["Сколько стоит?"]
        assert knowledge_repo.rebuilt == ["00000000-0000-0000-0000-000000000003"]
        assert knowledge_repo.actions[0]["action_type"] == "attach_question_to_entry"
        assert review_repo.marked == ["review_accepted"]
        assert queue_repo.enqueued[0]["task_type"] == "run_full_rag_eval"

    asyncio.run(run_test())


class _EntrySource:
    def __init__(self, entries: list[RagEvalEvidenceEntry]) -> None:
        self.entries = entries

    async def load_document_entries(
        self, *, project_id: str, document_id: str
    ) -> list[RagEvalEvidenceEntry]:
        return self.entries


class _FragmentGenerator:
    _model_name = "test-model"
    _max_concurrency = 2

    def __init__(
        self, events: list[tuple[str, str, float]], questions_per_entry: int = 1
    ) -> None:
        self.events = events
        self.questions_per_entry = questions_per_entry

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
        if entry.id == "entry_b":
            await asyncio.sleep(0.08)
        else:
            await asyncio.sleep(0.01)
        self.events.append(("generated", entry.id, perf_counter()))
        questions = [
            RagEvalQuestion(
                id=new_eval_id("question"),
                dataset_id="temporary_dataset",
                project_id=project_id,
                document_id=document_id,
                question=f"question {index} for {entry.id}",
                question_type=cast(RagEvalQuestionType, "paraphrase"),
                expected_entry_ids=[entry.id],
                expected_answer_summary=entry.content,
                should_answer=True,
                metadata={"source_chunk_id": entry.id},
            )
            for index in range(self.questions_per_entry)
        ]
        return RagEvalDataset(
            id=new_eval_id("dataset"),
            project_id=project_id,
            document_id=document_id,
            status="ready",
            model_used=self._model_name,
            total_questions=len(questions),
            questions=questions,
        )


class _TrackingRetriever:
    def __init__(self, events: list[tuple[str, str, float]]) -> None:
        self.events = events
        self.active = 0
        self.max_active = 0

    async def retrieve(
        self, *, project_id: str, question: str, limit: int
    ) -> list[RagEvalEvidenceEntry]:
        entry_id = "entry_b" if "entry_b" in question else "entry_a"
        self.events.append(("retrieval_started", entry_id, perf_counter()))
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        await asyncio.sleep(0.02)
        self.active -= 1
        self.events.append(("retrieval_finished", entry_id, perf_counter()))
        return [RagEvalEvidenceEntry(id=entry_id, content=f"answer {entry_id}")]


class _ProjectionStore:
    def __init__(self, events: list[tuple[str, str, float]]) -> None:
        self.events = events
        self.groups: list[dict[str, object]] = []
        self.results: list[RagEvalResult] = []
        self.questions: list[RagEvalQuestion] = []

    async def save_dataset(self, *, dataset: RagEvalDataset) -> None:
        return None

    async def save_questions(self, *, questions: list[RagEvalQuestion]) -> None:
        self.questions.extend(questions)

    async def create_run(self, *, run) -> None:
        return None

    async def save_result(self, *, result: RagEvalResult) -> None:
        self.results.append(result)

    async def save_report(self, *, report) -> None:
        return None

    async def finish_run(self, *, run) -> None:
        return None

    async def upsert_review_group(self, **kwargs) -> None:
        item = dict(kwargs)
        self.groups.append(item)
        if item.get("status") == "ready_for_review":
            self.events.append(
                ("group_ready", str(item["source_chunk_id"]), perf_counter())
            )


def test_fragment_group_ready_before_document_generation_completes() -> None:
    async def run_test() -> None:
        events: list[tuple[str, str, float]] = []
        entries = [
            RagEvalEvidenceEntry(id="entry_a", content="answer a"),
            RagEvalEvidenceEntry(id="entry_b", content="answer b"),
        ]
        retriever = _TrackingRetriever(events)
        store = _ProjectionStore(events)
        service = RagEvalService(
            entry_source=_EntrySource(entries),
            dataset_generator=_FragmentGenerator(events),
            runner=RagEvalRunner(retriever=retriever, mode="retrieval_eval"),
            reporter=RagQualityReporter(),
            store=store,
            run_concurrency=2,
            entry_retrieval_concurrency=2,
        )

        await service.generate_dataset_and_run_streaming_retrieval(
            project_id="00000000-0000-0000-0000-000000000001",
            document_id="00000000-0000-0000-0000-000000000002",
        )

        entry_a_ready = next(
            ts
            for event, entry_id, ts in events
            if event == "group_ready" and entry_id == "entry_a"
        )
        entry_b_generated = next(
            ts
            for event, entry_id, ts in events
            if event == "generated" and entry_id == "entry_b"
        )
        assert entry_a_ready < entry_b_generated
        assert any(
            group.get("status") == "generating_questions" for group in store.groups
        )
        assert any(
            group.get("status") == "checking_retrieval" for group in store.groups
        )
        assert any(group.get("status") == "ready_for_review" for group in store.groups)

    asyncio.run(run_test())


def test_per_entry_fanout_starts_after_entry_questions_are_generated() -> None:
    async def run_test() -> None:
        events: list[tuple[str, str, float]] = []
        entry = RagEvalEvidenceEntry(id="entry_a", content="answer a")
        retriever = _TrackingRetriever(events)
        store = _ProjectionStore(events)
        service = RagEvalService(
            entry_source=_EntrySource([entry]),
            dataset_generator=_FragmentGenerator(events, questions_per_entry=3),
            runner=RagEvalRunner(retriever=retriever, mode="retrieval_eval"),
            reporter=RagQualityReporter(),
            store=store,
            run_concurrency=3,
            entry_retrieval_concurrency=3,
        )

        await service.generate_dataset_and_run_streaming_retrieval(
            project_id="00000000-0000-0000-0000-000000000001",
            document_id="00000000-0000-0000-0000-000000000002",
        )

        generated_at = next(
            ts
            for event, entry_id, ts in events
            if event == "generated" and entry_id == "entry_a"
        )
        retrieval_starts = [
            ts
            for event, entry_id, ts in events
            if event == "retrieval_started" and entry_id == "entry_a"
        ]
        assert len(retrieval_starts) == 3
        assert all(started_at > generated_at for started_at in retrieval_starts)

    asyncio.run(run_test())


def test_global_retrieval_limiter_is_respected() -> None:
    async def run_test() -> None:
        events: list[tuple[str, str, float]] = []
        entry = RagEvalEvidenceEntry(id="entry_a", content="answer a")
        retriever = _TrackingRetriever(events)
        service = RagEvalService(
            entry_source=_EntrySource([entry]),
            dataset_generator=_FragmentGenerator(events, questions_per_entry=4),
            runner=RagEvalRunner(retriever=retriever, mode="retrieval_eval"),
            reporter=RagQualityReporter(),
            store=_ProjectionStore(events),
            run_concurrency=1,
            entry_retrieval_concurrency=4,
        )

        await service.generate_dataset_and_run_streaming_retrieval(
            project_id="00000000-0000-0000-0000-000000000001",
            document_id="00000000-0000-0000-0000-000000000002",
        )

        assert retriever.max_active == 1

    asyncio.run(run_test())


class _ProjectionReadRepo:
    async def get_latest_run_summary(self, *, project_id: str, document_id: str):
        return {
            "id": "run_running",
            "dataset_id": "dataset_1",
            "project_id": project_id,
            "document_id": document_id,
            "status": "running",
            "started_at": datetime.now(UTC).isoformat(),
            "finished_at": None,
            "retriever_version": "production_rag",
            "reranker_version": "production_rag",
            "generator_model": "test-model",
            "result_count": 1,
        }

    async def load_review_group_projections(self, *, run_id: str):
        return [
            {
                "source_chunk_id": "entry_a",
                "status": "ready_for_review",
                "questions_total": 1,
                "checked_questions": 1,
                "reliable_count": 1,
                "weak_count": 0,
                "confused_count": 0,
                "missing_count": 0,
                "improvement_count": 0,
                "review_payload": {
                    "entry_id": "entry_a",
                    "title": "Entry A",
                    "content": "answer a",
                    "question_count": 1,
                    "problem_count": 0,
                    "improvement_count": 0,
                    "status": "Надёжно находится",
                    "questions": [],
                    "existing_questions": [],
                    "proposed_improvements": [],
                },
            }
        ]


def test_latest_review_reads_projection_for_running_run() -> None:
    async def run_test() -> None:
        service = RagEvalReviewService(_ProjectionReadRepo())
        payload = await service.build_latest_review(
            project_id="00000000-0000-0000-0000-000000000001",
            document_id="00000000-0000-0000-0000-000000000002",
        )
        assert payload is not None
        assert payload["run"]["status"] == "running"
        assert payload["groups"][0]["entry_id"] == "entry_a"
        assert payload["groups"][0]["review_status"] == "ready_for_review"
        assert payload["summary"]["fragments_total"] == 1

    asyncio.run(run_test())
