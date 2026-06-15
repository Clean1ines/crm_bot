from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from types import ModuleType
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval import (
    WorkbenchRagEvalPromotionApplyResult,
    WorkbenchRagEvalPromotionBatchApplyResult,
    WorkbenchRagEvalPromotionCandidateDetails,
    WorkbenchRagEvalPromotionStatus,
    WorkbenchRagEvalQuestionDetails,
    WorkbenchRagEvalQuestionKind,
    WorkbenchRagEvalQuestionSource,
    WorkbenchRagEvalQuestionStatus,
    WorkbenchRagEvalRetrievalResultDetails,
    WorkbenchRagEvalRunStatus,
    WorkbenchRagEvalSummary,
)
from src.contexts.llm_runtime.application.ports.llm_dispatch_executor_port import (
    LlmDispatchExecutionInput,
    LlmDispatchExecutionResult,
)
from src.interfaces.http.knowledge import (
    get_llm_dispatch_executor,
    get_pool,
    get_project_repo,
    get_user_repository,
    router,
)


@dataclass(slots=True)
class FakeLlmDispatchExecutor:
    async def execute_dispatch(
        self,
        execution_input: LlmDispatchExecutionInput,
    ) -> LlmDispatchExecutionResult:
        raise AssertionError("HTTP test must not execute LLM")


def _summary() -> WorkbenchRagEvalSummary:
    now = datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)
    return WorkbenchRagEvalSummary(
        run_id="run-1",
        project_id="11111111-1111-1111-1111-111111111111",
        publication_id=None,
        source_document_ref=None,
        status=WorkbenchRagEvalRunStatus.COMPLETED,
        total_entries=1,
        total_questions=2,
        completed_questions=2,
        top1_hits=1,
        top3_hits=1,
        top5_hits=2,
        misses=0,
        promotion_candidate_count=0,
        created_at=now,
        completed_at=now,
        error_message=None,
    )


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)

    app.dependency_overrides[get_pool] = lambda: object()
    app.dependency_overrides[get_project_repo] = lambda: object()
    app.dependency_overrides[get_user_repository] = lambda: object()
    app.dependency_overrides[get_llm_dispatch_executor] = lambda: (
        FakeLlmDispatchExecutor()
    )

    return TestClient(app)


def test_workbench_rag_eval_run_endpoint_executes_use_case(monkeypatch) -> None:
    async def allow_access(**kwargs):
        del kwargs
        return None

    class FakeRunUseCase:
        async def execute(self, **kwargs):
            assert kwargs["project_id"] == "11111111-1111-1111-1111-111111111111"
            assert kwargs["publication_id"] == "publication-1"
            assert kwargs["source_document_ref"] is None
            assert kwargs["top_k"] == 5
            assert kwargs["max_entries"] == 20
            assert kwargs["allow_degraded_llama_instant"] is False
            return _summary()

    def fake_factory(**kwargs):
        assert "pool" in kwargs
        assert "llm_dispatch_executor" in kwargs
        return FakeRunUseCase()

    monkeypatch.setattr(
        "src.interfaces.http.knowledge._require_project_access", allow_access
    )
    composition_module = ModuleType("src.interfaces.composition.workbench_rag_eval")
    setattr(composition_module, "make_run_workbench_rag_eval", fake_factory)
    monkeypatch.setitem(
        sys.modules,
        "src.interfaces.composition.workbench_rag_eval",
        composition_module,
    )

    response = _client().post(
        "/api/projects/11111111-1111-1111-1111-111111111111/knowledge/rag-eval/workbench/run",
        json={"publication_id": "publication-1", "top_k": 5, "max_entries": 20},
    )

    assert response.status_code == 200
    assert response.json()["run"]["run_id"] == "run-1"


def test_workbench_rag_eval_run_endpoint_validates_top_k(monkeypatch) -> None:
    async def allow_access(**kwargs):
        del kwargs
        return None

    monkeypatch.setattr(
        "src.interfaces.http.knowledge._require_project_access", allow_access
    )

    response = _client().post(
        "/api/projects/11111111-1111-1111-1111-111111111111/knowledge/rag-eval/workbench/run",
        json={"top_k": 4, "max_entries": 20},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "top_k must be at least 5"


def test_workbench_rag_eval_run_endpoint_validates_max_entries(monkeypatch) -> None:
    async def allow_access(**kwargs):
        del kwargs
        return None

    monkeypatch.setattr(
        "src.interfaces.http.knowledge._require_project_access", allow_access
    )

    response = _client().post(
        "/api/projects/11111111-1111-1111-1111-111111111111/knowledge/rag-eval/workbench/run",
        json={"top_k": 5, "max_entries": 51},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "max_entries must be between 1 and 50"


def test_workbench_rag_eval_routes_are_in_knowledge_namespace() -> None:
    paths = {route.path for route in router.routes}

    assert "/api/projects/{project_id}/knowledge/rag-eval/workbench/run" in paths
    assert "/api/projects/{project_id}/knowledge/rag-eval/workbench/latest" in paths
    assert (
        "/api/projects/{project_id}/knowledge/rag-eval/workbench/runs/{run_id}" in paths
    )
    assert (
        "/api/projects/{project_id}/knowledge/rag-eval/workbench/runs/{run_id}/questions"
        in paths
    )
    assert (
        "/api/projects/{project_id}/knowledge/rag-eval/workbench/runs/{run_id}/promotion-candidates"
        in paths
    )


class FakeWorkbenchRagEvalRepository:
    def __init__(self, pool: object) -> None:
        self.pool = pool

    async def get_run(self, *, run_id: str, project_id: str):
        if run_id == "missing-run":
            return None
        return _summary()

    async def get_latest_run(self, *, project_id: str):
        return _summary()

    async def list_run_questions(self, *, project_id: str, run_id: str):
        now = datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)
        return (
            WorkbenchRagEvalQuestionDetails(
                question_id="question-1",
                run_id=run_id,
                project_id=project_id,
                expected_runtime_entry_id="entry-expected",
                expected_fact_id="fact-expected",
                question="Как спросить?",
                question_kind=WorkbenchRagEvalQuestionKind.PARAPHRASE,
                source=WorkbenchRagEvalQuestionSource.GENERATED,
                generation_model="model-1",
                prompt_version="prompt-v1",
                status=WorkbenchRagEvalQuestionStatus.CREATED,
                created_at=now,
                results=(
                    WorkbenchRagEvalRetrievalResultDetails(
                        result_id="result-1",
                        matched_runtime_entry_id="entry-expected",
                        matched_fact_id="fact-expected",
                        rank=1,
                        score=0.95,
                        top1_hit=True,
                        top3_hit=True,
                        top5_hit=True,
                        created_at=now,
                    ),
                ),
            ),
        )

    async def list_run_promotion_candidates(self, *, project_id: str, run_id: str):
        now = datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)
        return (
            WorkbenchRagEvalPromotionCandidateDetails(
                promotion_id="promotion-1",
                run_id=run_id,
                question_id="question-1",
                project_id=project_id,
                target_runtime_entry_id="entry-expected",
                target_fact_id="fact-expected",
                question="Как спросить?",
                status=WorkbenchRagEvalPromotionStatus.CANDIDATE,
                created_at=now,
                applied_at=None,
            ),
        )


def test_workbench_rag_eval_questions_endpoint_returns_questions(monkeypatch) -> None:
    async def allow_access(**kwargs):
        del kwargs
        return None

    monkeypatch.setattr(
        "src.interfaces.http.knowledge._require_project_access", allow_access
    )
    monkeypatch.setattr(
        "src.interfaces.http.knowledge.PostgresWorkbenchRagEvalRepository",
        FakeWorkbenchRagEvalRepository,
    )

    response = _client().get(
        "/api/projects/11111111-1111-1111-1111-111111111111/knowledge/rag-eval/workbench/runs/run-1/questions",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["questions"][0]["question_id"] == "question-1"
    assert (
        payload["questions"][0]["results"][0]["matched_runtime_entry_id"]
        == "entry-expected"
    )
    assert "answer_text" not in str(payload)


def test_workbench_rag_eval_candidates_endpoint_returns_candidates(monkeypatch) -> None:
    async def allow_access(**kwargs):
        del kwargs
        return None

    monkeypatch.setattr(
        "src.interfaces.http.knowledge._require_project_access", allow_access
    )
    monkeypatch.setattr(
        "src.interfaces.http.knowledge.PostgresWorkbenchRagEvalRepository",
        FakeWorkbenchRagEvalRepository,
    )

    response = _client().get(
        "/api/projects/11111111-1111-1111-1111-111111111111/knowledge/rag-eval/workbench/runs/run-1/promotion-candidates",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["candidates"][0]["promotion_id"] == "promotion-1"
    assert payload["candidates"][0]["status"] == "candidate"
    assert "answer_text" not in str(payload)


def test_workbench_rag_eval_details_endpoints_return_404_for_missing_run(
    monkeypatch,
) -> None:
    async def allow_access(**kwargs):
        del kwargs
        return None

    monkeypatch.setattr(
        "src.interfaces.http.knowledge._require_project_access", allow_access
    )
    monkeypatch.setattr(
        "src.interfaces.http.knowledge.PostgresWorkbenchRagEvalRepository",
        FakeWorkbenchRagEvalRepository,
    )

    questions = _client().get(
        "/api/projects/11111111-1111-1111-1111-111111111111/knowledge/rag-eval/workbench/runs/missing-run/questions",
    )
    candidates = _client().get(
        "/api/projects/11111111-1111-1111-1111-111111111111/knowledge/rag-eval/workbench/runs/missing-run/promotion-candidates",
    )

    assert questions.status_code == 404
    assert candidates.status_code == 404


class FakeApplyPromotionUseCase:
    async def execute(self, *, project_id: str, promotion_id: str, applied_at):
        del applied_at
        return WorkbenchRagEvalPromotionApplyResult(
            promotion_id=promotion_id,
            run_id="run-1",
            question_id="question-1",
            project_id=project_id,
            target_runtime_entry_id="entry-1",
            target_fact_id="fact-1",
            question="Как спросить иначе?",
            status=WorkbenchRagEvalPromotionStatus.APPLIED,
            possible_question_count=3,
            embedding_model_id="test-model",
            embedding_count=1,
            applied_at=_summary().completed_at or _summary().created_at,
        )


def test_workbench_rag_eval_apply_candidate_endpoint(monkeypatch) -> None:
    async def allow_access(**kwargs):
        del kwargs
        return None

    def fake_factory(**kwargs):
        assert "pool" in kwargs
        return FakeApplyPromotionUseCase()

    composition_module = ModuleType("src.interfaces.composition.workbench_rag_eval")
    setattr(composition_module, "make_apply_workbench_rag_eval_promotion", fake_factory)
    monkeypatch.setitem(
        sys.modules,
        "src.interfaces.composition.workbench_rag_eval",
        composition_module,
    )
    monkeypatch.setattr(
        "src.interfaces.http.knowledge._require_project_access", allow_access
    )

    response = _client().post(
        "/api/projects/11111111-1111-1111-1111-111111111111/knowledge/rag-eval/workbench/promotion-candidates/promotion-1/apply",
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["result"]["promotion_id"] == "promotion-1"
    assert payload["result"]["status"] == "applied"
    assert payload["result"]["embedding_count"] == 1
    assert "answer_text" not in str(payload)


def test_workbench_rag_eval_run_endpoint_rejects_non_bool_degraded_flag(
    monkeypatch,
) -> None:
    async def allow_access(**kwargs):
        del kwargs
        return None

    monkeypatch.setattr(
        "src.interfaces.http.knowledge._require_project_access", allow_access
    )

    response = _client().post(
        "/api/projects/11111111-1111-1111-1111-111111111111/knowledge/rag-eval/workbench/run",
        json={"top_k": 5, "max_entries": 20, "allow_degraded_llama_instant": "yes"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "allow_degraded_llama_instant must be boolean"


class FakeApplyPromotionsBatchUseCase:
    async def execute(
        self,
        *,
        project_id: str,
        mode: str,
        promotion_ids: tuple[str, ...],
        run_id: str | None,
        applied_at,
    ):
        del applied_at
        assert project_id == "11111111-1111-1111-1111-111111111111"
        assert mode == "selected"
        assert promotion_ids == ("promotion-1", "promotion-2")
        assert run_id is None
        return WorkbenchRagEvalPromotionBatchApplyResult(
            requested_count=2,
            applied_count=2,
            skipped_count=0,
            embedding_recalculation_count=1,
            errors=(),
        )


def test_workbench_rag_eval_apply_batch_endpoint(monkeypatch) -> None:
    async def allow_access(**kwargs):
        del kwargs
        return None

    def fake_factory(**kwargs):
        assert "pool" in kwargs
        return FakeApplyPromotionsBatchUseCase()

    composition_module = ModuleType("src.interfaces.composition.workbench_rag_eval")
    setattr(
        composition_module,
        "make_apply_workbench_rag_eval_promotions_batch",
        fake_factory,
    )
    monkeypatch.setitem(
        sys.modules,
        "src.interfaces.composition.workbench_rag_eval",
        composition_module,
    )
    monkeypatch.setattr(
        "src.interfaces.http.knowledge._require_project_access", allow_access
    )

    response = _client().post(
        "/api/projects/11111111-1111-1111-1111-111111111111/knowledge/rag-eval/workbench/promotion-candidates/apply-batch",
        json={"mode": "selected", "promotion_ids": ["promotion-1", "promotion-2"]},
    )

    assert response.status_code == 200
    payload = response.json()["result"]
    assert payload["requested_count"] == 2
    assert payload["applied_count"] == 2
    assert payload["embedding_recalculation_count"] == 1
