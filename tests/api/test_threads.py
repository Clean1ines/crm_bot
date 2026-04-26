import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.application.services.thread_query_service import ThreadQueryService
from fastapi.testclient import TestClient
from uuid import uuid4

from src.domain.project_plane.memory_views import MemoryEntryView
from src.domain.project_plane.thread_views import ThreadWithProjectView
from src.interfaces.http.app import app
from src.interfaces.http.dependencies import (
    get_current_user_id,
    get_thread_query_service,
    get_thread_command_service,
    get_project_repo,
    get_event_repo,
    get_memory_repository,
    get_orchestrator,
)


@pytest.fixture(autouse=True)
def mock_lifespan_pool():
    """Мокаем глобальный пул соединений, чтобы избежать RuntimeError."""
    with patch("src.interfaces.composition.fastapi_lifespan.pool", MagicMock()):
        yield


@pytest.fixture(autouse=True)
def reset_dependency_overrides():
    """После каждого теста сбрасываем переопределения зависимостей."""
    original_overrides = app.dependency_overrides.copy()
    yield
    app.dependency_overrides.clear()
    app.dependency_overrides.update(original_overrides)


@pytest.fixture(autouse=True)
def mock_orchestrator():
    """Мокаем get_orchestrator, чтобы избежать ошибок инициализации."""
    mock = AsyncMock()
    app.dependency_overrides[get_orchestrator] = lambda: mock
    yield
    # Очистка будет выполнена reset_dependency_overrides


@pytest.fixture
def client():
    return TestClient(app)



def make_thread_query_service(mock_thread_repo, *, event_repo=None, memory_repo=None):
    return ThreadQueryService(
        thread_read_repo=mock_thread_repo,
        thread_message_repo=mock_thread_repo,
        thread_runtime_state_repo=mock_thread_repo,
        event_repo=event_repo or AsyncMock(),
        memory_repo=memory_repo or AsyncMock(),
    )


class FakeTimelineThreadQueryService:
    def __init__(self, *, thread_repo, event_repo):
        self.thread_repo = thread_repo
        self.event_repo = event_repo

    async def get_thread_view(self, thread_id: str):
        return await self.thread_repo.get_thread_with_project_view(thread_id)

    async def get_timeline(self, thread_id: str, limit: int, offset: int):
        events = await self.event_repo.get_events_for_thread(thread_id, limit, offset)
        return {"events": events}


class FakeMemoryThreadQueryService:
    def __init__(self, *, thread_repo, memory_repo):
        self.thread_repo = thread_repo
        self.memory_repo = memory_repo

    async def get_thread_view(self, thread_id: str):
        return await self.thread_repo.get_thread_with_project_view(thread_id)

    async def get_memory(self, project_id: str, client_id: str | None, *, limit: int = 100):
        if not client_id:
            return {"items": []}
        items = await self.memory_repo.get_for_user_view(
            project_id=project_id,
            client_id=client_id,
            limit=limit,
        )
        return {
            "items": [
                item.to_record() if hasattr(item, "to_record") else item
                for item in items
            ]
        }

class TestThreadsAPI:
    # ------------------------------------------------------------------
    # Helpers for auth override
    # ------------------------------------------------------------------
    def _override_auth(self, user_id: str):
        """Подменяем get_current_user_id, чтобы возвращал заданный user_id."""
        async def override():
            return user_id
        app.dependency_overrides[get_current_user_id] = override

    def _restore_auth(self):
        """Восстанавливаем оригинальную зависимость (очистка делается автоматически)."""
        # Фикстура reset_dependency_overrides уже очистит всё, так что ничего не делаем
        pass

    # ------------------------------------------------------------------
    # GET /api/threads
    # ------------------------------------------------------------------
    def test_list_dialogs_success(self, client):
        user_id = str(uuid4())
        project_id = str(uuid4())
        self._override_auth(user_id)

        mock_project_repo = AsyncMock()
        mock_project_repo.user_has_project_role = AsyncMock(return_value=True)

        mock_thread_repo = AsyncMock()
        mock_thread_repo.get_dialogs = AsyncMock(return_value=[
            {
                "thread_id": str(uuid4()),
                "status": "active",
                "interaction_mode": "normal",
                "thread_created_at": "2025-01-01T12:00:00",
                "thread_updated_at": "2025-01-02T12:00:00",
                "client": {"id": str(uuid4()), "full_name": "John", "username": "john", "chat_id": 123},
                "last_message": {"content": "Hello", "created_at": "2025-01-02T12:00:00"},
                "unread_count": 0,
            }
        ])

        app.dependency_overrides[get_project_repo] = lambda: mock_project_repo
        app.dependency_overrides[get_thread_query_service] = lambda: make_thread_query_service(mock_thread_repo)

        response = client.get("/api/threads", params={"project_id": project_id})
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["thread_id"] is not None
        mock_thread_repo.get_dialogs.assert_awaited_once_with(
            project_id,
            limit=20,
            offset=0,
            status_filter=None,
            search=None,
        )

        # Убираем переопределения (фикстура сделает это автоматически)
        self._restore_auth()

    def test_list_dialogs_unauthorized(self, client):
        response = client.get("/api/threads", params={"project_id": str(uuid4())})
        assert response.status_code == 401

    def test_list_dialogs_forbidden_project_not_found(self, client):
        user_id = str(uuid4())
        project_id = str(uuid4())
        self._override_auth(user_id)

        mock_project_repo = AsyncMock()
        mock_project_repo.user_has_project_role = AsyncMock(return_value=False)
        mock_project_repo.get_project_view = AsyncMock(return_value=None)

        app.dependency_overrides[get_project_repo] = lambda: mock_project_repo
        app.dependency_overrides[get_thread_query_service] = lambda: make_thread_query_service(AsyncMock())

        response = client.get("/api/threads", params={"project_id": project_id})
        assert response.status_code == 403
        assert response.json()["detail"] == "Access denied"

        self._restore_auth()

    def test_list_dialogs_forbidden_wrong_user(self, client):
        user_id = str(uuid4())
        project_id = str(uuid4())
        self._override_auth(user_id)

        mock_project_repo = AsyncMock()
        mock_project_repo.user_has_project_role = AsyncMock(return_value=False)
        mock_project_repo.get_project_view = AsyncMock(return_value=None)

        app.dependency_overrides[get_project_repo] = lambda: mock_project_repo

        response = client.get("/api/threads", params={"project_id": project_id})
        assert response.status_code == 403
        assert response.json()["detail"] == "Access denied"

        self._restore_auth()

    def test_list_dialogs_validation_limit_out_of_range(self, client):
        user_id = str(uuid4())
        project_id = str(uuid4())
        self._override_auth(user_id)

        response = client.get("/api/threads", params={"project_id": project_id, "limit": 0})
        assert response.status_code == 422
        errors = response.json()["detail"]
        assert any(err["loc"] == ["query", "limit"] for err in errors)

        response = client.get("/api/threads", params={"project_id": project_id, "limit": 101})
        assert response.status_code == 422
        errors = response.json()["detail"]
        assert any(err["loc"] == ["query", "limit"] for err in errors)

        response = client.get("/api/threads", params={"project_id": project_id, "offset": -1})
        assert response.status_code == 422
        errors = response.json()["detail"]
        assert any(err["loc"] == ["query", "offset"] for err in errors)

        self._restore_auth()

    def test_list_dialogs_validation_missing_project_id(self, client):
        self._override_auth(str(uuid4()))
        try:
            response = client.get("/api/threads")
            assert response.status_code == 422
            errors = response.json()["detail"]
            assert any(err["loc"] == ["query", "project_id"] for err in errors)
        finally:
            self._restore_auth()

    # ------------------------------------------------------------------
    # GET /api/threads/{thread_id}/messages
    # ------------------------------------------------------------------
    def test_get_messages_success(self, client):
        user_id = str(uuid4())
        thread_id = str(uuid4())
        project_id = str(uuid4())
        self._override_auth(user_id)

        mock_thread_repo = AsyncMock()
        mock_thread_repo.get_thread_with_project_view = AsyncMock(return_value=ThreadWithProjectView(
            thread_id=thread_id,
            project_id=project_id,
        ))
        mock_thread_repo.get_messages = AsyncMock(return_value=[
            {"id": str(uuid4()), "role": "user", "content": "Hi", "created_at": "2025-01-01T12:00:00", "metadata": {}},
            {"id": str(uuid4()), "role": "assistant", "content": "Hello", "created_at": "2025-01-01T12:01:00", "metadata": {}},
        ])

        mock_project_repo = AsyncMock()
        mock_project_repo.user_has_project_role = AsyncMock(return_value=True)

        app.dependency_overrides[get_thread_query_service] = lambda: make_thread_query_service(mock_thread_repo)
        app.dependency_overrides[get_project_repo] = lambda: mock_project_repo

        response = client.get(f"/api/threads/{thread_id}/messages")
        assert response.status_code == 200
        data = response.json()
        assert "messages" in data
        assert len(data["messages"]) == 2
        mock_thread_repo.get_thread_with_project_view.assert_awaited_once_with(thread_id)
        mock_thread_repo.get_messages.assert_awaited_once_with(thread_id, 20, 0)

        self._restore_auth()

    def test_get_messages_unauthorized(self, client):
        response = client.get(f"/api/threads/{uuid4()}/messages")
        assert response.status_code == 401

    def test_get_messages_thread_not_found(self, client):
        user_id = str(uuid4())
        thread_id = str(uuid4())
        self._override_auth(user_id)

        mock_thread_repo = AsyncMock()
        mock_thread_repo.get_thread_with_project_view = AsyncMock(return_value=None)

        app.dependency_overrides[get_thread_query_service] = lambda: make_thread_query_service(mock_thread_repo)

        response = client.get(f"/api/threads/{thread_id}/messages")
        assert response.status_code == 404
        assert response.json()["detail"] == "Thread not found"

        self._restore_auth()

    def test_get_messages_forbidden(self, client):
        user_id = str(uuid4())
        thread_id = str(uuid4())
        project_id = str(uuid4())
        self._override_auth(user_id)

        mock_thread_repo = AsyncMock()
        mock_thread_repo.get_thread_with_project_view = AsyncMock(return_value=ThreadWithProjectView(
            thread_id=thread_id,
            project_id=project_id,
        ))

        mock_project_repo = AsyncMock()
        mock_project_repo.user_has_project_role = AsyncMock(return_value=False)
        mock_project_repo.get_project_view = AsyncMock(return_value=None)

        app.dependency_overrides[get_thread_query_service] = lambda: make_thread_query_service(mock_thread_repo)
        app.dependency_overrides[get_project_repo] = lambda: mock_project_repo

        response = client.get(f"/api/threads/{thread_id}/messages")
        assert response.status_code == 403
        assert response.json()["detail"] == "Access denied"

        self._restore_auth()

    def test_get_messages_validation_limit_out_of_range(self, client):
        user_id = str(uuid4())
        thread_id = str(uuid4())
        self._override_auth(user_id)

        response = client.get(f"/api/threads/{thread_id}/messages", params={"limit": 0})
        assert response.status_code == 422
        errors = response.json()["detail"]
        assert any(err["loc"] == ["query", "limit"] for err in errors)

        response = client.get(f"/api/threads/{thread_id}/messages", params={"limit": 101})
        assert response.status_code == 422
        errors = response.json()["detail"]
        assert any(err["loc"] == ["query", "limit"] for err in errors)

        response = client.get(f"/api/threads/{thread_id}/messages", params={"offset": -1})
        assert response.status_code == 422
        errors = response.json()["detail"]
        assert any(err["loc"] == ["query", "offset"] for err in errors)

        self._restore_auth()

    # ------------------------------------------------------------------
    # POST /api/threads/{thread_id}/reply
    # ------------------------------------------------------------------
    def test_reply_success(self, client):
        user_id = str(uuid4())
        thread_id = str(uuid4())
        project_id = str(uuid4())
        self._override_auth(user_id)

        mock_thread_repo = AsyncMock()
        mock_thread_repo.get_thread_with_project_view = AsyncMock(return_value=ThreadWithProjectView(
            thread_id=thread_id,
            project_id=project_id,
            status="manual",
        ))

        mock_project_repo = AsyncMock()
        mock_project_repo.user_has_project_role = AsyncMock(return_value=True)

        mock_orchestrator = AsyncMock()
        mock_orchestrator.manager_reply = AsyncMock(return_value=True)

        app.dependency_overrides[get_thread_query_service] = lambda: make_thread_query_service(mock_thread_repo)
        app.dependency_overrides[get_project_repo] = lambda: mock_project_repo
        app.dependency_overrides[get_orchestrator] = lambda: mock_orchestrator

        payload = {"message": "Hello manager reply"}
        response = client.post(f"/api/threads/{thread_id}/reply", json=payload)
        assert response.status_code == 200
        assert response.json() == {"status": "sent"}

        mock_thread_repo.get_thread_with_project_view.assert_awaited_once_with(thread_id)
        mock_orchestrator.manager_reply.assert_awaited_once_with(
            thread_id,
            "Hello manager reply",
            manager_chat_id=None,
            manager_user_id=user_id,
        )

        self._restore_auth()

    def test_reply_unauthorized(self, client):
        response = client.post(f"/api/threads/{uuid4()}/reply", json={"message": "test"})
        assert response.status_code == 401

    def test_reply_thread_not_found(self, client):
        user_id = str(uuid4())
        thread_id = str(uuid4())
        self._override_auth(user_id)

        mock_thread_repo = AsyncMock()
        mock_thread_repo.get_thread_with_project_view = AsyncMock(return_value=None)

        app.dependency_overrides[get_thread_query_service] = lambda: make_thread_query_service(mock_thread_repo)

        response = client.post(f"/api/threads/{thread_id}/reply", json={"message": "test"})
        assert response.status_code == 404
        assert response.json()["detail"] == "Thread not found"

        self._restore_auth()

    def test_reply_forbidden(self, client):
        user_id = str(uuid4())
        thread_id = str(uuid4())
        project_id = str(uuid4())
        self._override_auth(user_id)

        mock_thread_repo = AsyncMock()
        mock_thread_repo.get_thread_with_project_view = AsyncMock(return_value=ThreadWithProjectView(
            thread_id=thread_id,
            project_id=project_id,
        ))

        mock_project_repo = AsyncMock()
        mock_project_repo.user_has_project_role = AsyncMock(return_value=False)
        mock_project_repo.get_project_view = AsyncMock(return_value=None)

        app.dependency_overrides[get_thread_query_service] = lambda: make_thread_query_service(mock_thread_repo)
        app.dependency_overrides[get_project_repo] = lambda: mock_project_repo

        response = client.post(f"/api/threads/{thread_id}/reply", json={"message": "test"})
        assert response.status_code == 403
        assert response.json()["detail"] == "Access denied"

        self._restore_auth()

    def test_reply_not_manual(self, client):
        user_id = str(uuid4())
        thread_id = str(uuid4())
        project_id = str(uuid4())
        self._override_auth(user_id)

        mock_thread_repo = AsyncMock()
        mock_thread_repo.get_thread_with_project_view = AsyncMock(return_value=ThreadWithProjectView(
            thread_id=thread_id,
            project_id=project_id,
            status="active",
        ))

        mock_project_repo = AsyncMock()
        mock_project_repo.user_has_project_role = AsyncMock(return_value=True)

        app.dependency_overrides[get_thread_query_service] = lambda: make_thread_query_service(mock_thread_repo)
        app.dependency_overrides[get_project_repo] = lambda: mock_project_repo

        response = client.post(f"/api/threads/{thread_id}/reply", json={"message": "test"})
        assert response.status_code == 400
        assert response.json()["detail"] == "Thread is not in manual mode"

        self._restore_auth()

    def test_reply_user_without_linked_telegram_still_allowed(self, client):
        user_id = str(uuid4())
        thread_id = str(uuid4())
        project_id = str(uuid4())
        self._override_auth(user_id)

        mock_thread_repo = AsyncMock()
        mock_thread_repo.get_thread_with_project_view = AsyncMock(return_value=ThreadWithProjectView(
            thread_id=thread_id,
            project_id=project_id,
            status="manual",
        ))

        mock_project_repo = AsyncMock()
        mock_project_repo.user_has_project_role = AsyncMock(return_value=True)

        mock_orchestrator = AsyncMock()
        mock_orchestrator.manager_reply = AsyncMock(return_value=True)

        app.dependency_overrides[get_thread_query_service] = lambda: make_thread_query_service(mock_thread_repo)
        app.dependency_overrides[get_project_repo] = lambda: mock_project_repo
        app.dependency_overrides[get_orchestrator] = lambda: mock_orchestrator

        response = client.post(f"/api/threads/{thread_id}/reply", json={"message": "test"})
        assert response.status_code == 200
        assert response.json() == {"status": "sent"}
        mock_orchestrator.manager_reply.assert_awaited_once_with(
            thread_id,
            "test",
            manager_chat_id=None,
            manager_user_id=user_id,
        )

        self._restore_auth()

    def test_reply_validation_missing_message(self, client):
        user_id = str(uuid4())
        thread_id = str(uuid4())
        self._override_auth(user_id)

        response = client.post(f"/api/threads/{thread_id}/reply", json={})
        assert response.status_code == 422
        errors = response.json()["detail"]
        assert any(err["loc"] == ["body", "message"] for err in errors)

        self._restore_auth()

    # ------------------------------------------------------------------
    # GET /api/threads/{thread_id}/timeline
    # ------------------------------------------------------------------
    def test_timeline_success(self, client):
        user_id = str(uuid4())
        thread_id = str(uuid4())
        project_id = str(uuid4())
        self._override_auth(user_id)

        mock_thread_repo = AsyncMock()
        mock_thread_repo.get_thread_with_project_view = AsyncMock(return_value=ThreadWithProjectView(
            thread_id=thread_id,
            project_id=project_id,
        ))

        mock_project_repo = AsyncMock()
        mock_project_repo.user_has_project_role = AsyncMock(return_value=True)

        mock_event_repo = AsyncMock()
        mock_event_repo.get_events_for_thread = AsyncMock(return_value=[
            {"id": 1, "type": "message_received", "payload": {"text": "Hello"}, "ts": "2025-01-01T12:00:00"},
        ])

        mock_thread_query_service = FakeTimelineThreadQueryService(
            thread_repo=mock_thread_repo,
            event_repo=mock_event_repo,
        )

        app.dependency_overrides[get_thread_query_service] = lambda: mock_thread_query_service
        app.dependency_overrides[get_project_repo] = lambda: mock_project_repo
        app.dependency_overrides[get_event_repo] = lambda: mock_event_repo

        response = client.get(f"/api/threads/{thread_id}/timeline")
        assert response.status_code == 200
        data = response.json()
        assert "events" in data
        assert len(data["events"]) == 1

        mock_event_repo.get_events_for_thread.assert_awaited_once_with(thread_id, 30, 0)

        self._restore_auth()

    def test_timeline_unauthorized(self, client):
        response = client.get(f"/api/threads/{uuid4()}/timeline")
        assert response.status_code == 401

    def test_timeline_thread_not_found(self, client):
        user_id = str(uuid4())
        thread_id = str(uuid4())
        self._override_auth(user_id)

        mock_thread_repo = AsyncMock()
        mock_thread_repo.get_thread_with_project_view = AsyncMock(return_value=None)

        app.dependency_overrides[get_thread_query_service] = lambda: make_thread_query_service(mock_thread_repo)

        response = client.get(f"/api/threads/{thread_id}/timeline")
        assert response.status_code == 404
        assert response.json()["detail"] == "Thread not found"

        self._restore_auth()

    def test_timeline_forbidden(self, client):
        user_id = str(uuid4())
        thread_id = str(uuid4())
        project_id = str(uuid4())
        self._override_auth(user_id)

        mock_thread_repo = AsyncMock()
        mock_thread_repo.get_thread_with_project_view = AsyncMock(return_value=ThreadWithProjectView(
            thread_id=thread_id,
            project_id=project_id,
        ))

        mock_project_repo = AsyncMock()
        mock_project_repo.user_has_project_role = AsyncMock(return_value=False)
        mock_project_repo.get_project_view = AsyncMock(return_value=None)

        app.dependency_overrides[get_thread_query_service] = lambda: make_thread_query_service(mock_thread_repo)
        app.dependency_overrides[get_project_repo] = lambda: mock_project_repo

        response = client.get(f"/api/threads/{thread_id}/timeline")
        assert response.status_code == 403
        assert response.json()["detail"] == "Access denied"

        self._restore_auth()

    # ------------------------------------------------------------------
    # GET /api/threads/{thread_id}/memory
    # ------------------------------------------------------------------
    def test_get_memory_success(self, client):
        user_id = str(uuid4())
        thread_id = str(uuid4())
        project_id = str(uuid4())
        client_id = str(uuid4())
        self._override_auth(user_id)

        mock_thread_repo = AsyncMock()
        mock_thread_repo.get_thread_with_project_view = AsyncMock(return_value=ThreadWithProjectView(
            thread_id=thread_id,
            project_id=project_id,
            client_id=client_id,
        ))

        mock_project_repo = AsyncMock()
        mock_project_repo.user_has_project_role = AsyncMock(return_value=True)

        mock_memory_repo = AsyncMock()
        mock_memory_repo.get_for_user_view = AsyncMock(return_value=[
            MemoryEntryView(id=str(uuid4()), key="pref", value="yes", type="preference"),
        ])

        app.dependency_overrides[get_thread_query_service] = lambda: FakeMemoryThreadQueryService(
            thread_repo=mock_thread_repo,
            memory_repo=mock_memory_repo,
        )
        app.dependency_overrides[get_project_repo] = lambda: mock_project_repo

        response = client.get(f"/api/threads/{thread_id}/memory")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert len(data["items"]) == 1

        mock_memory_repo.get_for_user_view.assert_awaited_once_with(
            project_id=project_id, client_id=client_id, limit=100
        )

        self._restore_auth()

    def test_get_memory_no_client_id(self, client):
        user_id = str(uuid4())
        thread_id = str(uuid4())
        project_id = str(uuid4())
        self._override_auth(user_id)

        mock_thread_repo = AsyncMock()
        mock_thread_repo.get_thread_with_project_view = AsyncMock(return_value=ThreadWithProjectView(
            thread_id=thread_id,
            project_id=project_id,
            client_id=None,
        ))

        mock_project_repo = AsyncMock()
        mock_project_repo.user_has_project_role = AsyncMock(return_value=True)

        app.dependency_overrides[get_thread_query_service] = lambda: make_thread_query_service(mock_thread_repo)
        app.dependency_overrides[get_project_repo] = lambda: mock_project_repo

        response = client.get(f"/api/threads/{thread_id}/memory")
        assert response.status_code == 200
        assert response.json() == {"items": []}

        self._restore_auth()

    def test_get_memory_unauthorized(self, client):
        response = client.get(f"/api/threads/{uuid4()}/memory")
        assert response.status_code == 401

    def test_get_memory_thread_not_found(self, client):
        user_id = str(uuid4())
        thread_id = str(uuid4())
        self._override_auth(user_id)

        mock_thread_repo = AsyncMock()
        mock_thread_repo.get_thread_with_project_view = AsyncMock(return_value=None)

        app.dependency_overrides[get_thread_query_service] = lambda: make_thread_query_service(mock_thread_repo)

        response = client.get(f"/api/threads/{thread_id}/memory")
        assert response.status_code == 404
        assert response.json()["detail"] == "Thread not found"

        self._restore_auth()

    def test_get_memory_forbidden(self, client):
        user_id = str(uuid4())
        thread_id = str(uuid4())
        project_id = str(uuid4())
        self._override_auth(user_id)

        mock_thread_repo = AsyncMock()
        mock_thread_repo.get_thread_with_project_view = AsyncMock(return_value=ThreadWithProjectView(
            thread_id=thread_id,
            project_id=project_id,
        ))

        mock_project_repo = AsyncMock()
        mock_project_repo.user_has_project_role = AsyncMock(return_value=False)
        mock_project_repo.get_project_view = AsyncMock(return_value=None)

        app.dependency_overrides[get_thread_query_service] = lambda: make_thread_query_service(mock_thread_repo)
        app.dependency_overrides[get_project_repo] = lambda: mock_project_repo

        response = client.get(f"/api/threads/{thread_id}/memory")
        assert response.status_code == 403
        assert response.json()["detail"] == "Access denied"

        self._restore_auth()

    # ------------------------------------------------------------------
    # PATCH /api/threads/{thread_id}/memory
    # ------------------------------------------------------------------
    def test_update_memory_success(self, client):
        user_id = str(uuid4())
        thread_id = str(uuid4())
        project_id = str(uuid4())
        client_id = str(uuid4())
        self._override_auth(user_id)

        mock_thread_repo = AsyncMock()
        mock_thread_repo.get_thread_with_project_view = AsyncMock(return_value=ThreadWithProjectView(
            thread_id=thread_id,
            project_id=project_id,
            client_id=client_id,
        ))

        mock_project_repo = AsyncMock()
        mock_project_repo.user_has_project_role = AsyncMock(return_value=True)

        mock_thread_command_service = AsyncMock()
        mock_thread_command_service.update_memory_entry = AsyncMock(return_value={"ok": True})

        app.dependency_overrides[get_thread_query_service] = lambda: make_thread_query_service(mock_thread_repo)
        app.dependency_overrides[get_thread_command_service] = lambda: mock_thread_command_service
        app.dependency_overrides[get_project_repo] = lambda: mock_project_repo

        payload = {"key": "preference", "value": "yes"}
        response = client.patch(f"/api/threads/{thread_id}/memory", json=payload)
        if response.status_code != 200:
            print("Response body:", response.text)
        assert response.status_code == 200
        assert response.json() == {"ok": True}

        mock_thread_command_service.update_memory_entry.assert_awaited_once_with(
            project_id=project_id,
            client_id=client_id,
            key="preference",
            value="yes",
        )

        self._restore_auth()

    def test_update_memory_no_client_id(self, client):
        user_id = str(uuid4())
        thread_id = str(uuid4())
        project_id = str(uuid4())
        self._override_auth(user_id)

        mock_thread_repo = AsyncMock()
        mock_thread_repo.get_thread_with_project_view = AsyncMock(return_value=ThreadWithProjectView(
            thread_id=thread_id,
            project_id=project_id,
            client_id=None,
        ))

        mock_project_repo = AsyncMock()
        mock_project_repo.user_has_project_role = AsyncMock(return_value=True)

        app.dependency_overrides[get_thread_query_service] = lambda: make_thread_query_service(mock_thread_repo)
        app.dependency_overrides[get_project_repo] = lambda: mock_project_repo

        payload = {"key": "pref", "value": "yes"}
        response = client.patch(f"/api/threads/{thread_id}/memory", json=payload)
        if response.status_code != 400:
            print("Response body:", response.text)
        assert response.status_code == 400
        assert response.json()["detail"] == "No client associated with thread"

        self._restore_auth()

    def test_update_memory_unauthorized(self, client):
        response = client.patch(f"/api/threads/{uuid4()}/memory", json={"key": "k", "value": "v"})
        assert response.status_code == 401

    def test_update_memory_success(self, client):
        user_id = str(uuid4())
        thread_id = str(uuid4())
        project_id = str(uuid4())
        client_id = str(uuid4())
        self._override_auth(user_id)

        mock_thread_repo = AsyncMock()
        mock_thread_repo.get_thread_with_project_view = AsyncMock(return_value=ThreadWithProjectView(
            thread_id=thread_id,
            project_id=project_id,
            client_id=client_id,
        ))

        mock_project_repo = AsyncMock()
        mock_project_repo.user_has_project_role = AsyncMock(return_value=True)

        mock_thread_command_service = AsyncMock()
        mock_thread_command_service.update_memory_entry = AsyncMock(return_value={"ok": True})

        app.dependency_overrides[get_thread_query_service] = lambda: make_thread_query_service(mock_thread_repo)
        app.dependency_overrides[get_thread_command_service] = lambda: mock_thread_command_service
        app.dependency_overrides[get_project_repo] = lambda: mock_project_repo

        payload = {"key": "preference", "value": '{"text": "yes"}'}
        response = client.patch(f"/api/threads/{thread_id}/memory", json=payload)
        assert response.status_code == 200
        assert response.json() == {"ok": True}

        mock_thread_command_service.update_memory_entry.assert_awaited_once_with(
            project_id=project_id,
            client_id=client_id,
            key="preference",
            value={"text": "yes"},  # Pydantic Json парсит строку в объект
        )

        self._restore_auth()

    def test_update_memory_no_client_id(self, client):
        user_id = str(uuid4())
        thread_id = str(uuid4())
        project_id = str(uuid4())
        self._override_auth(user_id)

        mock_thread_repo = AsyncMock()
        mock_thread_repo.get_thread_with_project_view = AsyncMock(return_value=ThreadWithProjectView(
            thread_id=thread_id,
            project_id=project_id,
            client_id=None,
        ))

        mock_project_repo = AsyncMock()
        mock_project_repo.user_has_project_role = AsyncMock(return_value=True)

        app.dependency_overrides[get_thread_query_service] = lambda: make_thread_query_service(mock_thread_repo)
        app.dependency_overrides[get_project_repo] = lambda: mock_project_repo

        payload = {"key": "pref", "value": '{"text": "yes"}'}  # FIXED: send string JSON
        response = client.patch(f"/api/threads/{thread_id}/memory", json=payload)
        assert response.status_code == 400
        assert response.json()["detail"] == "No client associated with thread"

        self._restore_auth()
    # ------------------------------------------------------------------
    # GET /api/threads/{thread_id}/state
    # ------------------------------------------------------------------
    def test_get_state_success(self, client):
        user_id = str(uuid4())
        thread_id = str(uuid4())
        project_id = str(uuid4())
        self._override_auth(user_id)

        mock_thread_repo = AsyncMock()
        mock_thread_repo.get_thread_with_project_view = AsyncMock(return_value=ThreadWithProjectView(
            thread_id=thread_id,
            project_id=project_id,
        ))
        mock_thread_repo.get_state_json = AsyncMock(return_value={"key": "value"})

        mock_project_repo = AsyncMock()
        mock_project_repo.user_has_project_role = AsyncMock(return_value=True)

        app.dependency_overrides[get_thread_query_service] = lambda: make_thread_query_service(mock_thread_repo)
        app.dependency_overrides[get_project_repo] = lambda: mock_project_repo

        response = client.get(f"/api/threads/{thread_id}/state")
        assert response.status_code == 200
        assert response.json() == {"state": {"key": "value"}}

        mock_thread_repo.get_state_json.assert_awaited_once_with(thread_id)

        self._restore_auth()

    def test_get_state_unauthorized(self, client):
        response = client.get(f"/api/threads/{uuid4()}/state")
        assert response.status_code == 401

    def test_get_state_thread_not_found(self, client):
        user_id = str(uuid4())
        thread_id = str(uuid4())
        self._override_auth(user_id)

        mock_thread_repo = AsyncMock()
        mock_thread_repo.get_thread_with_project_view = AsyncMock(return_value=None)

        app.dependency_overrides[get_thread_query_service] = lambda: make_thread_query_service(mock_thread_repo)

        response = client.get(f"/api/threads/{thread_id}/state")
        assert response.status_code == 404
        assert response.json()["detail"] == "Thread not found"

        self._restore_auth()

    def test_get_state_forbidden(self, client):
        user_id = str(uuid4())
        thread_id = str(uuid4())
        project_id = str(uuid4())
        self._override_auth(user_id)

        mock_thread_repo = AsyncMock()
        mock_thread_repo.get_thread_with_project_view = AsyncMock(return_value=ThreadWithProjectView(
            thread_id=thread_id,
            project_id=project_id,
        ))

        mock_project_repo = AsyncMock()
        mock_project_repo.user_has_project_role = AsyncMock(return_value=False)
        mock_project_repo.get_project_view = AsyncMock(return_value=None)

        app.dependency_overrides[get_thread_query_service] = lambda: make_thread_query_service(mock_thread_repo)
        app.dependency_overrides[get_project_repo] = lambda: mock_project_repo

        response = client.get(f"/api/threads/{thread_id}/state")
        assert response.status_code == 403
        assert response.json()["detail"] == "Access denied"

        self._restore_auth()

    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
