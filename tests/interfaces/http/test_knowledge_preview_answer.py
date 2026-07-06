from __future__ import annotations

from dataclasses import dataclass
from types import ModuleType
import inspect
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.interfaces.http.knowledge import (
    get_pool,
    get_project_repo,
    get_user_repository,
    preview_knowledge,
    router,
)


@dataclass(frozen=True, slots=True)
class FakePreviewResult:
    def to_dict(self) -> dict[str, object]:
        return {
            "query": "Когда доставка?",
            "answer": "Доставка занимает два дня.",
            "is_empty": False,
            "method": "client_answer_preview",
            "retrieval_mode": "runtime_equivalent",
            "debug_context": {
                "facts": [
                    {
                        "id": "runtime-entry-1",
                        "content": "Полный опубликованный факт.",
                        "score": 0.9,
                        "method": "runtime_hybrid",
                        "source": "runtime",
                        "title": None,
                        "entry_kind": "faq_workbench_fact",
                    }
                ]
            },
            "facts": [],
        }


class FakePreviewService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def execute(self, **kwargs) -> FakePreviewResult:
        self.calls.append(kwargs)
        return FakePreviewResult()


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_pool] = lambda: object()
    app.dependency_overrides[get_project_repo] = lambda: object()
    app.dependency_overrides[get_user_repository] = lambda: object()
    return TestClient(app)


def test_knowledge_preview_route_calls_answer_preview_service(monkeypatch) -> None:
    async def allow_access(**kwargs):
        del kwargs
        return None

    fake_service = FakePreviewService()

    def fake_factory(pool):
        assert pool is not None
        return fake_service

    monkeypatch.setattr(
        "src.interfaces.http.knowledge._require_project_access",
        allow_access,
    )
    composition_module = ModuleType("src.interfaces.composition.project_answer_preview")
    setattr(composition_module, "make_project_answer_preview_service", fake_factory)
    monkeypatch.setitem(
        sys.modules,
        "src.interfaces.composition.project_answer_preview",
        composition_module,
    )

    response = _client().post(
        "/api/projects/project-1/knowledge/preview",
        json={"question": "Когда доставка?", "limit": 5},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["answer"] == "Доставка занимает два дня."
    assert payload["method"] == "client_answer_preview"
    assert fake_service.calls == [
        {"project_id": "project-1", "question": "Когда доставка?", "limit": 5}
    ]


def test_knowledge_preview_route_rejects_empty_question(monkeypatch) -> None:
    async def allow_access(**kwargs):
        del kwargs
        return None

    monkeypatch.setattr(
        "src.interfaces.http.knowledge._require_project_access",
        allow_access,
    )

    response = _client().post(
        "/api/projects/project-1/knowledge/preview",
        json={"question": "   "},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "question must be non-empty string"


def test_knowledge_preview_route_does_not_use_conversation_orchestrator() -> None:
    source = inspect.getsource(preview_knowledge)

    assert "_legacy_endpoint_gone" not in source
    assert "ConversationOrchestrator" not in source
    assert "process_message" not in source
