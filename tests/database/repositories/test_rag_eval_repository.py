from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from src.application.rag_eval.failure_classification import (
    KnowledgeEditAction,
    KnowledgeEditActionType,
)
from src.application.rag_eval.schemas import (
    RagEvalDataset,
    RagEvalQuestion,
    RagEvalResult,
    RagEvalRun,
    RagEvalEvidenceEntry,
    RagQualityReport,
)
from src.infrastructure.db.repositories.rag_eval_repository import RagEvalRepository


PROJECT_ID = "00000000-0000-0000-0000-000000000001"
DOCUMENT_ID = "00000000-0000-0000-0000-000000000002"


class FakeAcquire:
    def __init__(self, conn: FakeConn) -> None:
        self.conn = conn

    async def __aenter__(self) -> FakeConn:
        return self.conn

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class FakePool:
    def __init__(self, conn: FakeConn) -> None:
        self.conn = conn

    def acquire(self) -> FakeAcquire:
        return FakeAcquire(self.conn)


class FakeConn:
    def __init__(self) -> None:
        self.execute_calls: list[tuple[str, tuple[object, ...]]] = []
        self.executemany_calls: list[tuple[str, list[tuple[object, ...]]]] = []
        self.fetch_rows: list[dict[str, object]] = []
        self.fetchrow_result: dict[str, object] | None = None

    async def execute(self, sql: str, *args: object) -> None:
        self.execute_calls.append((sql, args))

    async def executemany(self, sql: str, records: list[tuple[object, ...]]) -> None:
        self.executemany_calls.append((sql, records))

    async def fetch(self, sql: str, *args: object) -> list[dict[str, object]]:
        self.execute_calls.append((sql, args))
        return self.fetch_rows

    async def fetchrow(self, sql: str, *args: object) -> dict[str, object] | None:
        self.execute_calls.append((sql, args))
        return self.fetchrow_result


@pytest.mark.asyncio
async def test_load_document_entries_maps_retrieval_surface_rows() -> None:
    conn = FakeConn()
    conn.fetch_rows = [
        {
            "id": "chunk_1",
            "content": "Подключение занимает 1 день.",
            "document_id": DOCUMENT_ID,
            "source": "kb.md",
            "entry_kind": "faq_answer",
            "title": "Подключение",
            "source_refs": [
                {
                    "quote": "excerpt",
                    "source_index": 0,
                    "source_chunk_id": f"{DOCUMENT_ID}:0",
                    "confidence": 1.0,
                }
            ],
            "embedding_text": "Подключение срок",
            "questions": ["Сколько подключение?"],
            "synonyms": ["запуск"],
            "tags": ["onboarding"],
        }
    ]

    repo = RagEvalRepository(FakePool(conn))
    chunks = await repo.load_document_entries(
        project_id=PROJECT_ID,
        document_id=DOCUMENT_ID,
    )

    assert len(chunks) == 1
    assert chunks[0].id == "chunk_1"
    assert chunks[0].content == "Подключение занимает 1 день."
    assert chunks[0].metadata["title"] == "Подключение"
    assert chunks[0].source_refs[0].quote == "excerpt"
    assert chunks[0].source_refs[0].source_index == 0
    assert chunks[0].source_refs[0].source_chunk_id == f"{DOCUMENT_ID}:0"
    assert chunks[0].metadata["source_refs"] == [
        {
            "quote": "excerpt",
            "source_index": 0,
            "source_chunk_id": f"{DOCUMENT_ID}:0",
            "confidence": 1.0,
        }
    ]
    assert "FROM knowledge_retrieval_surface AS rs" in conn.execute_calls[0][0]
    assert "knowledge_base" not in conn.execute_calls[0][0]


@pytest.mark.asyncio
async def test_save_dataset_persists_dataset_and_questions() -> None:
    conn = FakeConn()
    repo = RagEvalRepository(FakePool(conn))

    question = RagEvalQuestion(
        id="question_1",
        dataset_id="dataset_1",
        project_id=PROJECT_ID,
        document_id=DOCUMENT_ID,
        question="Сколько занимает подключение?",
        question_type="direct",
        expected_entry_ids=["chunk_1"],
        expected_answer_summary="Подключение занимает 1 день.",
        should_answer=True,
        metadata={"why": "direct evidence"},
    )
    dataset = RagEvalDataset(
        id="dataset_1",
        project_id=PROJECT_ID,
        document_id=DOCUMENT_ID,
        status="ready",
        model_used="fake-model",
        total_questions=1,
        questions=[question],
        metadata={"source": "test"},
    )

    await repo.save_dataset(dataset=dataset)

    assert "INSERT INTO rag_eval_datasets" in conn.execute_calls[0][0]
    assert conn.execute_calls[0][1][0] == "dataset_1"
    assert conn.execute_calls[0][1][6] == 1

    assert len(conn.executemany_calls) == 1
    sql, records = conn.executemany_calls[0]
    assert "INSERT INTO rag_eval_questions" in sql
    assert records[0][0] == "question_1"
    assert json.loads(records[0][6]) == ["chunk_1"]
    assert json.loads(records[0][13]) == {"why": "direct evidence"}


@pytest.mark.asyncio
async def test_save_result_persists_metrics_and_judge_json() -> None:
    conn = FakeConn()
    repo = RagEvalRepository(FakePool(conn))

    question = RagEvalQuestion(
        id="question_1",
        dataset_id="dataset_1",
        project_id=PROJECT_ID,
        document_id=DOCUMENT_ID,
        question="Сколько занимает подключение?",
        question_type="direct",
        expected_entry_ids=["chunk_1"],
        expected_answer_summary="Подключение занимает 1 день.",
        should_answer=True,
    )

    result = RagEvalResult(
        id="result_1",
        run_id="run_1",
        question_id="question_1",
        question=question,
        retrieved_entries=[
            RagEvalEvidenceEntry(id="chunk_1", content="Подключение занимает 1 день.")
        ],
        answer_text="Подключение занимает 1 день.",
        top1_hit=True,
        top3_hit=True,
        top5_hit=True,
        expected_entry_found=True,
        wrong_entry_top1=False,
        answer_supported=True,
        hallucination_risk="low",
        should_answer_passed=True,
        score=0.99,
        notes="ok",
        judge_json={"answer_supported": True},
        latency_ms=123,
    )

    await repo.save_result(result=result)

    sql, args = conn.execute_calls[0]
    assert "INSERT INTO rag_eval_results" in sql
    assert args[0] == "result_1"
    assert json.loads(args[3]) == ["chunk_1"]
    assert args[13] == 0.99
    assert json.loads(args[15]) == {"answer_supported": True}


@pytest.mark.asyncio
async def test_create_and_finish_run_update_run_state() -> None:
    conn = FakeConn()
    repo = RagEvalRepository(FakePool(conn))

    run = RagEvalRun(
        id="run_1",
        dataset_id="dataset_1",
        project_id=PROJECT_ID,
        document_id=DOCUMENT_ID,
        status="running",
        generator_model="fake-model",
    )

    await repo.create_run(run=run)

    assert "INSERT INTO rag_eval_runs" in conn.execute_calls[0][0]
    assert conn.execute_calls[0][1][0] == "run_1"

    finished = RagEvalRun(
        id="run_1",
        dataset_id="dataset_1",
        project_id=PROJECT_ID,
        document_id=DOCUMENT_ID,
        status="completed",
        finished_at=datetime.now(UTC),
        generator_model="fake-model",
    )

    await repo.finish_run(run=finished)

    assert "UPDATE rag_eval_runs" in conn.execute_calls[1][0]
    assert conn.execute_calls[1][1][0] == "run_1"
    assert conn.execute_calls[1][1][1] == "completed"


@pytest.mark.asyncio
async def test_save_and_get_latest_report() -> None:
    conn = FakeConn()
    repo = RagEvalRepository(FakePool(conn))

    report = RagQualityReport(
        id="report_1",
        run_id="run_1",
        dataset_id="dataset_1",
        project_id=PROJECT_ID,
        document_id=DOCUMENT_ID,
        score=88.5,
        readiness="needs_review",
        strengths=["retrieval ok"],
        problems=["one wrong entry"],
        recommendations=["split sections"],
        metrics={"top3_rate": 90.0},
        markdown="# Report",
    )

    await repo.save_report(report=report)

    sql, args = conn.execute_calls[0]
    assert "INSERT INTO rag_quality_reports" in sql
    assert args[0] == "report_1"
    assert json.loads(args[7]) == ["retrieval ok"]
    assert json.loads(args[10]) == {"top3_rate": 90.0}

    conn.fetchrow_result = {
        "id": "report_1",
        "run_id": "run_1",
        "dataset_id": "dataset_1",
        "project_id": PROJECT_ID,
        "document_id": DOCUMENT_ID,
        "score": 88.5,
        "readiness": "needs_review",
        "strengths": ["retrieval ok"],
        "problems": ["one wrong entry"],
        "recommendations": ["split sections"],
        "metrics": {"top3_rate": 90.0},
        "markdown": "# Report",
        "created_at": "2026-05-05T11:10:00Z",
    }

    latest = await repo.get_latest_report(
        project_id=PROJECT_ID,
        document_id=DOCUMENT_ID,
    )

    assert latest is not None
    assert latest["id"] == "report_1"
    assert latest["score"] == 88.5
    assert latest["readiness"] == "needs_review"


@pytest.mark.asyncio
async def test_get_latest_report_includes_actionable_results_without_raw_evidence() -> (
    None
):
    conn = FakeConn()
    repo = RagEvalRepository(FakePool(conn))

    created_at = datetime.now(UTC)
    action = KnowledgeEditAction(
        action_type=KnowledgeEditActionType.ATTACH_QUESTION_TO_ENTRY,
        target_entry_id="00000000-0000-0000-0000-000000000003",
        reason="Attach missing user wording to canonical entry.",
        payload={
            "question": "Как подключить менеджера к проекту?",
            "embedding_text": "INTERNAL_EMBEDDING_TEXT_MUST_NOT_LEAK",
        },
    )

    conn.fetchrow_result = {
        "id": "report_1",
        "run_id": "run_1",
        "dataset_id": "dataset_1",
        "project_id": PROJECT_ID,
        "document_id": DOCUMENT_ID,
        "score": 61.0,
        "readiness": "needs_review",
        "strengths": ["some evidence found"],
        "problems": ["missing wording"],
        "recommendations": ["apply proposed actions"],
        "metrics": {"top3_rate": 60.0},
        "markdown": "# Report",
        "created_at": "2026-05-05T11:10:00Z",
    }
    conn.fetch_rows = [
        {
            "id": "result_1",
            "run_id": "run_1",
            "question_id": "question_1",
            "retrieved_entry_ids": ["00000000-0000-0000-0000-000000000004"],
            "top1_hit": False,
            "top3_hit": False,
            "top5_hit": False,
            "expected_entry_found": False,
            "wrong_entry_top1": True,
            "classification": None,
            "proposed_actions": [action.to_json()],
            "answer_text": "Raw generated answer must not be exposed here.",
            "answer_supported": False,
            "hallucination_risk": "high",
            "should_answer_passed": False,
            "score": 0.25,
            "notes": "debug notes should stay out of actionable summary",
            "judge_json": {
                "retrieved_entry_ids": ["00000000-0000-0000-0000-000000000004"],
                "embedding_text": "JUDGE_INTERNAL_EMBEDDING_TEXT_MUST_NOT_LEAK",
            },
            "latency_ms": 123,
            "created_at": created_at,
            "q_id": "question_1",
            "q_dataset_id": "dataset_1",
            "q_project_id": PROJECT_ID,
            "q_document_id": DOCUMENT_ID,
            "q_question": "Как подключить менеджера?",
            "q_question_type": "direct",
            "q_expected_entry_ids": ["00000000-0000-0000-0000-000000000003"],
            "q_expected_answer_summary": "Менеджера можно подключить в настройках проекта.",
            "q_should_answer": True,
            "q_should_escalate": False,
            "q_difficulty": 1,
            "q_severity": "medium",
            "q_source": "llm_generated",
            "q_metadata": {"source_chunk_ids": ["legacy-source-ref"]},
            "q_created_at": created_at,
        }
    ]

    latest = await repo.get_latest_report(
        project_id=PROJECT_ID,
        document_id=DOCUMENT_ID,
    )

    assert latest is not None
    actionable_results = latest["actionable_results"]
    assert isinstance(actionable_results, list)
    assert len(actionable_results) == 1

    item = actionable_results[0]
    assert isinstance(item, dict)
    assert item["result_id"] == "result_1"
    assert item["run_id"] == "run_1"
    assert item["question_id"] == "question_1"
    assert item["question"] == "Как подключить менеджера?"
    assert item["expected_entry_ids"] == ["00000000-0000-0000-0000-000000000003"]
    assert item["retrieved_entry_ids"] == ["00000000-0000-0000-0000-000000000004"]
    assert item["answer_supported"] is False
    assert item["wrong_entry_top1"] is True
    assert item["hallucination_risk"] == "high"

    proposed_actions = item["proposed_actions"]
    assert isinstance(proposed_actions, list)
    assert proposed_actions[0]["action_type"] == "attach_question_to_entry"
    assert (
        proposed_actions[0]["target_entry_id"] == "00000000-0000-0000-0000-000000000003"
    )
    assert proposed_actions[0]["payload"] == {
        "question": "Как подключить менеджера к проекту?"
    }

    rendered = repr(latest)
    assert "INTERNAL_EMBEDDING_TEXT_MUST_NOT_LEAK" not in rendered
    assert "JUDGE_INTERNAL_EMBEDDING_TEXT_MUST_NOT_LEAK" not in rendered
    assert "Raw generated answer must not be exposed here." not in rendered
    assert "debug notes should stay out of actionable summary" not in rendered

    assert "SELECT" in conn.execute_calls[0][0]
    assert "FROM rag_quality_reports" in conn.execute_calls[0][0]
    assert "FROM rag_eval_results AS rr" in conn.execute_calls[1][0]
