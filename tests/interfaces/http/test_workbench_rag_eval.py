from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.interfaces.http.knowledge import (
    get_pool,
    get_project_repo,
    get_user_repository,
    router,
)


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)

    app.dependency_overrides[get_pool] = lambda: object()
    app.dependency_overrides[get_project_repo] = lambda: object()
    app.dependency_overrides[get_user_repository] = lambda: object()

    return TestClient(app)


def test_workbench_rag_eval_run_endpoint_is_backend_guarded(monkeypatch) -> None:
    async def allow_access(**kwargs):
        del kwargs
        return None

    monkeypatch.setattr(
        "src.interfaces.http.knowledge._require_project_access", allow_access
    )

    response = _client().post(
        "/api/projects/11111111-1111-1111-1111-111111111111/knowledge/rag-eval/workbench/run",
        json={"top_k": 5, "max_entries": 20},
    )

    assert response.status_code == 501
    assert (
        "production question generation is not connected yet"
        in response.json()["detail"]
    )


def test_workbench_rag_eval_routes_are_in_knowledge_namespace() -> None:
    paths = {route.path for route in router.routes}

    assert "/api/projects/{project_id}/knowledge/rag-eval/workbench/run" in paths
    assert "/api/projects/{project_id}/knowledge/rag-eval/workbench/latest" in paths
    assert (
        "/api/projects/{project_id}/knowledge/rag-eval/workbench/runs/{run_id}" in paths
    )
