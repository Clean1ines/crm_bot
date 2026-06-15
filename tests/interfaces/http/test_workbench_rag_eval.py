from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from types import ModuleType
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.contexts.knowledge_workbench.rag_eval.application.models.workbench_rag_eval import (
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
