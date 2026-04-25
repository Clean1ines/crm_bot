from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.interfaces.http.chat import _visitor_chat_id
from src.interfaces.http.dependencies import get_orchestrator, get_project_repo
from src.interfaces.http.app import app


@pytest.fixture(autouse=True)
def mock_lifespan_pool():
    with patch("src.infrastructure.app.lifespan.pool", MagicMock()):
        yield


@pytest.fixture(autouse=True)
def reset_dependency_overrides():
    original_overrides = app.dependency_overrides.copy()
    yield
    app.dependency_overrides.clear()
    app.dependency_overrides.update(original_overrides)


@pytest.fixture
def client():
    return TestClient(app)


def test_client_chat_uses_project_plane_message_pipeline(client):
    project_id = "project-1"
    visitor_id = "visitor-1"
    project_repo = AsyncMock()
    project_repo.project_exists = AsyncMock(return_value=True)
    orchestrator = AsyncMock()
    orchestrator.process_message = AsyncMock(return_value="hello from ai")

    app.dependency_overrides[get_project_repo] = lambda: project_repo
    app.dependency_overrides[get_orchestrator] = lambda: orchestrator

    response = client.post(
        f"/api/chat/projects/{project_id}",
        json={
            "message": "hello",
            "visitor_id": visitor_id,
            "username": "web_user",
            "full_name": "Web User",
        },
    )

    assert response.status_code == 200
    assert response.text == "hello from ai"
    project_repo.project_exists.assert_awaited_once_with(project_id)
    orchestrator.process_message.assert_awaited_once_with(
        project_id=project_id,
        chat_id=_visitor_chat_id(project_id, visitor_id),
        text="hello",
        username="web_user",
        full_name="Web User",
        source="web",
    )


def test_client_chat_returns_404_for_unknown_project(client):
    project_repo = AsyncMock()
    project_repo.project_exists = AsyncMock(return_value=False)
    orchestrator = AsyncMock()

    app.dependency_overrides[get_project_repo] = lambda: project_repo
    app.dependency_overrides[get_orchestrator] = lambda: orchestrator

    response = client.post("/api/chat/projects/missing", json={"message": "hello"})

    assert response.status_code == 404
    orchestrator.process_message.assert_not_called()
