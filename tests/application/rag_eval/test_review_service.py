from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import cast


from src.application.rag_eval.failure_classification import (
    KnowledgeEditAction,
    KnowledgeEditActionType,
)
from src.application.rag_eval.review_service import (
    RagEvalReviewService,
    build_review_payload,
)
from src.application.rag_eval.schemas import (
    RagEvalEvidenceEntry,
    RagEvalQuestion,
    RagEvalQuestionType,
    RagEvalResult,
)


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
