import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from uuid import uuid4

from src.main import app
from src.api.dependencies import get_current_user_id, get_project_repo
from src.database.repositories.project_repository import ProjectRepository


@pytest.fixture(autouse=True)
def mock_lifespan_pool():
    """Mock global pool to avoid RuntimeError."""
    with patch("src.core.lifespan.pool", MagicMock()):
        yield


@pytest.fixture
def client():
    return TestClient(app)


class TestProjectsAPI:
    # ------------------------------------------------------------------
    # Helpers for auth override
    # ------------------------------------------------------------------
    def _override_auth(self, user_id: str):
        async def override():
            return user_id
        self._original_auth = app.dependency_overrides.get(get_current_user_id)
        app.dependency_overrides[get_current_user_id] = override

    def _restore_auth(self):
        if self._original_auth is not None:
            app.dependency_overrides[get_current_user_id] = self._original_auth
        else:
            app.dependency_overrides.pop(get_current_user_id, None)

    # ------------------------------------------------------------------
    # GET /api/projects
    # ------------------------------------------------------------------
    def test_list_projects_success(self, client):
        user_id = str(uuid4())
        self._override_auth(user_id)
        try:
            mock_repo = AsyncMock(spec=ProjectRepository)
            mock_repo.get_projects_by_user_id = AsyncMock(return_value=[
                {"id": str(uuid4()), "name": "Proj1", "is_pro_mode": False, "template_slug": None,
                 "user_id": user_id, "client_bot_username": None, "manager_bot_username": None},
                {"id": str(uuid4()), "name": "Proj2", "is_pro_mode": True, "template_slug": "support",
                 "user_id": user_id, "client_bot_username": "bot1", "manager_bot_username": None},
            ])
            mock_repo.get_managers = AsyncMock(side_effect=[["123", "456"], ["789"]])

            original = app.dependency_overrides.get(get_project_repo)
            app.dependency_overrides[get_project_repo] = lambda: mock_repo

            response = client.get("/api/projects")
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2
            assert data[0]["name"] == "Proj1"
            assert data[0]["managers"] == [123, 456]
            assert data[1]["managers"] == [789]
            assert data[1]["client_bot_username"] == "bot1"

            mock_repo.get_projects_by_user_id.assert_awaited_once_with(user_id)
            assert mock_repo.get_managers.call_count == 2

            if original:
                app.dependency_overrides[get_project_repo] = original
            else:
                app.dependency_overrides.pop(get_project_repo, None)
        finally:
            self._restore_auth()

    def test_list_projects_unauthorized(self, client):
        response = client.get("/api/projects")
        assert response.status_code == 401
        assert response.json()["detail"] == "Authorization header required"

    # ------------------------------------------------------------------
    # POST /api/projects
    # ------------------------------------------------------------------
    def test_create_project_success(self, client):
        user_id = str(uuid4())
        self._override_auth(user_id)
        try:
            mock_repo = AsyncMock(spec=ProjectRepository)
            project_id = str(uuid4())
            mock_repo.create_project_with_user_id = AsyncMock(return_value=project_id)
            mock_repo.get_project_by_id = AsyncMock(return_value={
                "id": project_id, "name": "New Project", "is_pro_mode": False, "template_slug": None,
                "user_id": user_id, "client_bot_username": None, "manager_bot_username": None
            })
            mock_repo.get_managers = AsyncMock(return_value=[])

            app.dependency_overrides[get_project_repo] = lambda: mock_repo

            payload = {"name": "New Project"}
            response = client.post("/api/projects", json=payload)
            assert response.status_code == 201
            data = response.json()
            assert data["id"] == project_id
            assert data["name"] == "New Project"
            assert data["managers"] == []
            assert data["user_id"] == user_id

            mock_repo.create_project_with_user_id.assert_awaited_once_with(user_id, "New Project")
            mock_repo.get_project_by_id.assert_awaited_once_with(project_id)
            mock_repo.get_managers.assert_awaited_once_with(project_id)

            app.dependency_overrides.pop(get_project_repo, None)
        finally:
            self._restore_auth()

    def test_create_project_creation_failed(self, client):
        user_id = str(uuid4())
        self._override_auth(user_id)
        try:
            mock_repo = AsyncMock(spec=ProjectRepository)
            project_id = str(uuid4())
            mock_repo.create_project_with_user_id = AsyncMock(return_value=project_id)
            mock_repo.get_project_by_id = AsyncMock(return_value=None)

            app.dependency_overrides[get_project_repo] = lambda: mock_repo

            payload = {"name": "New Project"}
            response = client.post("/api/projects", json=payload)
            assert response.status_code == 500
            assert response.json()["detail"] == "Project creation failed"

            app.dependency_overrides.pop(get_project_repo, None)
        finally:
            self._restore_auth()

    def test_create_project_unauthorized(self, client):
        response = client.post("/api/projects", json={"name": "Test"})
        assert response.status_code == 401

    def test_create_project_missing_name(self, client):
        self._override_auth(str(uuid4()))
        try:
            response = client.post("/api/projects", json={})
            assert response.status_code == 422
            errors = response.json()["detail"]
            assert any(err["loc"] == ["body", "name"] for err in errors)
        finally:
            self._restore_auth()

    # ------------------------------------------------------------------
    # GET /api/projects/{project_id}
    # ------------------------------------------------------------------
    def test_get_project_success(self, client):
        user_id = str(uuid4())
        project_id = str(uuid4())
        self._override_auth(user_id)
        try:
            mock_repo = AsyncMock(spec=ProjectRepository)
            mock_repo.get_project_by_id = AsyncMock(return_value={
                "id": project_id, "name": "Test", "is_pro_mode": False, "template_slug": None,
                "user_id": user_id, "client_bot_username": None, "manager_bot_username": None
            })
            mock_repo.get_managers = AsyncMock(return_value=["111", "222"])

            app.dependency_overrides[get_project_repo] = lambda: mock_repo

            response = client.get(f"/api/projects/{project_id}")
            assert response.status_code == 200
            data = response.json()
            assert data["id"] == project_id
            assert data["managers"] == [111, 222]

            mock_repo.get_project_by_id.assert_awaited_once_with(project_id)
            mock_repo.get_managers.assert_awaited_once_with(project_id)

            app.dependency_overrides.pop(get_project_repo, None)
        finally:
            self._restore_auth()

    def test_get_project_not_found(self, client):
        user_id = str(uuid4())
        project_id = str(uuid4())
        self._override_auth(user_id)
        try:
            mock_repo = AsyncMock(spec=ProjectRepository)
            mock_repo.get_project_by_id = AsyncMock(return_value=None)

            app.dependency_overrides[get_project_repo] = lambda: mock_repo

            response = client.get(f"/api/projects/{project_id}")
            assert response.status_code == 404
            assert response.json()["detail"] == "Project not found"

            app.dependency_overrides.pop(get_project_repo, None)
        finally:
            self._restore_auth()

    def test_get_project_forbidden(self, client):
        user_id = str(uuid4())
        other_user_id = str(uuid4())
        project_id = str(uuid4())
        self._override_auth(user_id)
        try:
            mock_repo = AsyncMock(spec=ProjectRepository)
            mock_repo.get_project_by_id = AsyncMock(return_value={
                "id": project_id, "name": "Test", "user_id": other_user_id
            })

            app.dependency_overrides[get_project_repo] = lambda: mock_repo

            response = client.get(f"/api/projects/{project_id}")
            assert response.status_code == 403
            assert response.json()["detail"] == "Access denied"

            app.dependency_overrides.pop(get_project_repo, None)
        finally:
            self._restore_auth()

    def test_get_project_unauthorized(self, client):
        response = client.get(f"/api/projects/{uuid4()}")
        assert response.status_code == 401

    # ------------------------------------------------------------------
    # PUT /api/projects/{project_id}
    # ------------------------------------------------------------------
    def test_update_project_success(self, client):
        user_id = str(uuid4())
        project_id = str(uuid4())
        self._override_auth(user_id)
        try:
            mock_repo = AsyncMock(spec=ProjectRepository)
            mock_repo.project_exists = AsyncMock(return_value=True)
            # Первый вызов get_project_by_id для проверки владельца
            mock_repo.get_project_by_id = AsyncMock(side_effect=[
                {"id": project_id, "name": "Old", "user_id": user_id,
                 "is_pro_mode": False, "template_slug": None},   # добавлены обязательные поля
                {"id": project_id, "name": "Updated", "user_id": user_id,
                 "is_pro_mode": False, "template_slug": None}    # добавлены обязательные поля
            ])
            mock_repo.update_project = AsyncMock()
            mock_repo.get_managers = AsyncMock(return_value=[])

            app.dependency_overrides[get_project_repo] = lambda: mock_repo

            payload = {"name": "Updated"}
            response = client.put(f"/api/projects/{project_id}", json=payload)
            assert response.status_code == 200
            data = response.json()
            assert data["name"] == "Updated"

            mock_repo.project_exists.assert_awaited_once_with(project_id)
            mock_repo.update_project.assert_awaited_once_with(project_id, "Updated")
            mock_repo.get_managers.assert_awaited_once_with(project_id)

            app.dependency_overrides.pop(get_project_repo, None)
        finally:
            self._restore_auth()

    def test_update_project_not_found(self, client):
        user_id = str(uuid4())
        project_id = str(uuid4())
        self._override_auth(user_id)
        try:
            mock_repo = AsyncMock(spec=ProjectRepository)
            mock_repo.project_exists = AsyncMock(return_value=False)

            app.dependency_overrides[get_project_repo] = lambda: mock_repo

            response = client.put(f"/api/projects/{project_id}", json={"name": "x"})
            assert response.status_code == 404
            assert response.json()["detail"] == "Project not found"

            app.dependency_overrides.pop(get_project_repo, None)
        finally:
            self._restore_auth()

    def test_update_project_forbidden(self, client):
        user_id = str(uuid4())
        other_user_id = str(uuid4())
        project_id = str(uuid4())
        self._override_auth(user_id)
        try:
            mock_repo = AsyncMock(spec=ProjectRepository)
            mock_repo.project_exists = AsyncMock(return_value=True)
            mock_repo.get_project_by_id = AsyncMock(return_value={
                "id": project_id, "user_id": other_user_id
            })

            app.dependency_overrides[get_project_repo] = lambda: mock_repo

            response = client.put(f"/api/projects/{project_id}", json={"name": "x"})
            assert response.status_code == 403
            assert response.json()["detail"] == "Access denied"

            app.dependency_overrides.pop(get_project_repo, None)
        finally:
            self._restore_auth()

    def test_update_project_unauthorized(self, client):
        response = client.put(f"/api/projects/{uuid4()}", json={"name": "x"})
        assert response.status_code == 401

    # ------------------------------------------------------------------
    # DELETE /api/projects/{project_id}
    # ------------------------------------------------------------------
    def test_delete_project_success(self, client):
        user_id = str(uuid4())
        project_id = str(uuid4())
        self._override_auth(user_id)
        try:
            mock_repo = AsyncMock(spec=ProjectRepository)
            mock_repo.project_exists = AsyncMock(return_value=True)
            mock_repo.get_project_by_id = AsyncMock(return_value={
                "id": project_id, "user_id": user_id
            })
            mock_repo.delete_project = AsyncMock()

            app.dependency_overrides[get_project_repo] = lambda: mock_repo

            response = client.delete(f"/api/projects/{project_id}")
            assert response.status_code == 204
            assert response.content == b''

            mock_repo.delete_project.assert_awaited_once_with(project_id)

            app.dependency_overrides.pop(get_project_repo, None)
        finally:
            self._restore_auth()

    def test_delete_project_not_found(self, client):
        user_id = str(uuid4())
        project_id = str(uuid4())
        self._override_auth(user_id)
        try:
            mock_repo = AsyncMock(spec=ProjectRepository)
            mock_repo.project_exists = AsyncMock(return_value=False)

            app.dependency_overrides[get_project_repo] = lambda: mock_repo

            response = client.delete(f"/api/projects/{project_id}")
            assert response.status_code == 404
            assert response.json()["detail"] == "Project not found"

            app.dependency_overrides.pop(get_project_repo, None)
        finally:
            self._restore_auth()

    def test_delete_project_forbidden(self, client):
        user_id = str(uuid4())
        other_user_id = str(uuid4())
        project_id = str(uuid4())
        self._override_auth(user_id)
        try:
            mock_repo = AsyncMock(spec=ProjectRepository)
            mock_repo.project_exists = AsyncMock(return_value=True)
            mock_repo.get_project_by_id = AsyncMock(return_value={
                "id": project_id, "user_id": other_user_id
            })

            app.dependency_overrides[get_project_repo] = lambda: mock_repo

            response = client.delete(f"/api/projects/{project_id}")
            assert response.status_code == 403
            assert response.json()["detail"] == "Access denied"

            app.dependency_overrides.pop(get_project_repo, None)
        finally:
            self._restore_auth()

    def test_delete_project_unauthorized(self, client):
        response = client.delete(f"/api/projects/{uuid4()}")
        assert response.status_code == 401

    # ------------------------------------------------------------------
    # POST /api/projects/{project_id}/bot-token
    # ------------------------------------------------------------------
    def test_set_bot_token_success(self, client):
        user_id = str(uuid4())
        project_id = str(uuid4())
        self._override_auth(user_id)
        try:
            mock_repo = AsyncMock(spec=ProjectRepository)
            mock_repo.project_exists = AsyncMock(return_value=True)
            mock_repo.get_project_by_id = AsyncMock(return_value={
                "id": project_id, "user_id": user_id
            })
            mock_repo.set_bot_token = AsyncMock()

            app.dependency_overrides[get_project_repo] = lambda: mock_repo

            payload = {"token": "bot123:token"}
            response = client.post(f"/api/projects/{project_id}/bot-token", json=payload)
            assert response.status_code == 200
            assert response.json() == {"status": "ok"}

            mock_repo.set_bot_token.assert_awaited_once_with(project_id, "bot123:token")

            app.dependency_overrides.pop(get_project_repo, None)
        finally:
            self._restore_auth()

    def test_set_bot_token_not_found(self, client):
        user_id = str(uuid4())
        project_id = str(uuid4())
        self._override_auth(user_id)
        try:
            mock_repo = AsyncMock(spec=ProjectRepository)
            mock_repo.project_exists = AsyncMock(return_value=False)

            app.dependency_overrides[get_project_repo] = lambda: mock_repo

            response = client.post(f"/api/projects/{project_id}/bot-token", json={"token": "t"})
            assert response.status_code == 404
            assert response.json()["detail"] == "Project not found"

            app.dependency_overrides.pop(get_project_repo, None)
        finally:
            self._restore_auth()

    def test_set_bot_token_forbidden(self, client):
        user_id = str(uuid4())
        other_user_id = str(uuid4())
        project_id = str(uuid4())
        self._override_auth(user_id)
        try:
            mock_repo = AsyncMock(spec=ProjectRepository)
            mock_repo.project_exists = AsyncMock(return_value=True)
            mock_repo.get_project_by_id = AsyncMock(return_value={
                "id": project_id, "user_id": other_user_id
            })

            app.dependency_overrides[get_project_repo] = lambda: mock_repo

            response = client.post(f"/api/projects/{project_id}/bot-token", json={"token": "t"})
            assert response.status_code == 403
            assert response.json()["detail"] == "Access denied"

            app.dependency_overrides.pop(get_project_repo, None)
        finally:
            self._restore_auth()

    # ------------------------------------------------------------------
    # POST /api/projects/{project_id}/manager-token
    # ------------------------------------------------------------------
    def test_set_manager_token_success(self, client):
        user_id = str(uuid4())
        project_id = str(uuid4())
        self._override_auth(user_id)
        try:
            mock_repo = AsyncMock(spec=ProjectRepository)
            mock_repo.project_exists = AsyncMock(return_value=True)
            mock_repo.get_project_by_id = AsyncMock(return_value={
                "id": project_id, "user_id": user_id
            })
            mock_repo.set_manager_bot_token = AsyncMock()

            app.dependency_overrides[get_project_repo] = lambda: mock_repo

            payload = {"token": "man123:token"}
            response = client.post(f"/api/projects/{project_id}/manager-token", json=payload)
            assert response.status_code == 200
            assert response.json() == {"status": "ok"}

            mock_repo.set_manager_bot_token.assert_awaited_once_with(project_id, "man123:token")

            app.dependency_overrides.pop(get_project_repo, None)
        finally:
            self._restore_auth()

    def test_set_manager_token_not_found(self, client):
        user_id = str(uuid4())
        project_id = str(uuid4())
        self._override_auth(user_id)
        try:
            mock_repo = AsyncMock(spec=ProjectRepository)
            mock_repo.project_exists = AsyncMock(return_value=False)

            app.dependency_overrides[get_project_repo] = lambda: mock_repo

            response = client.post(f"/api/projects/{project_id}/manager-token", json={"token": "t"})
            assert response.status_code == 404
            assert response.json()["detail"] == "Project not found"

            app.dependency_overrides.pop(get_project_repo, None)
        finally:
            self._restore_auth()

    def test_set_manager_token_forbidden(self, client):
        user_id = str(uuid4())
        other_user_id = str(uuid4())
        project_id = str(uuid4())
        self._override_auth(user_id)
        try:
            mock_repo = AsyncMock(spec=ProjectRepository)
            mock_repo.project_exists = AsyncMock(return_value=True)
            mock_repo.get_project_by_id = AsyncMock(return_value={
                "id": project_id, "user_id": other_user_id
            })

            app.dependency_overrides[get_project_repo] = lambda: mock_repo

            response = client.post(f"/api/projects/{project_id}/manager-token", json={"token": "t"})
            assert response.status_code == 403
            assert response.json()["detail"] == "Access denied"

            app.dependency_overrides.pop(get_project_repo, None)
        finally:
            self._restore_auth()

    # ------------------------------------------------------------------
    # GET /api/projects/{project_id}/managers
    # ------------------------------------------------------------------
    def test_get_managers_success(self, client):
        user_id = str(uuid4())
        project_id = str(uuid4())
        self._override_auth(user_id)
        try:
            mock_repo = AsyncMock(spec=ProjectRepository)
            mock_repo.get_project_by_id = AsyncMock(return_value={
                "id": project_id, "user_id": user_id
            })
            mock_repo.get_managers = AsyncMock(return_value=["123", "456"])

            app.dependency_overrides[get_project_repo] = lambda: mock_repo

            response = client.get(f"/api/projects/{project_id}/managers")
            assert response.status_code == 200
            assert response.json() == [123, 456]

            mock_repo.get_managers.assert_awaited_once_with(project_id)

            app.dependency_overrides.pop(get_project_repo, None)
        finally:
            self._restore_auth()

    def test_get_managers_forbidden_no_project(self, client):
        user_id = str(uuid4())
        project_id = str(uuid4())
        self._override_auth(user_id)
        try:
            mock_repo = AsyncMock(spec=ProjectRepository)
            mock_repo.get_project_by_id = AsyncMock(return_value=None)

            app.dependency_overrides[get_project_repo] = lambda: mock_repo

            response = client.get(f"/api/projects/{project_id}/managers")
            assert response.status_code == 403
            assert response.json()["detail"] == "Access denied"

            app.dependency_overrides.pop(get_project_repo, None)
        finally:
            self._restore_auth()

    def test_get_managers_forbidden_wrong_user(self, client):
        user_id = str(uuid4())
        other_user_id = str(uuid4())
        project_id = str(uuid4())
        self._override_auth(user_id)
        try:
            mock_repo = AsyncMock(spec=ProjectRepository)
            mock_repo.get_project_by_id = AsyncMock(return_value={
                "id": project_id, "user_id": other_user_id
            })

            app.dependency_overrides[get_project_repo] = lambda: mock_repo

            response = client.get(f"/api/projects/{project_id}/managers")
            assert response.status_code == 403
            assert response.json()["detail"] == "Access denied"

            app.dependency_overrides.pop(get_project_repo, None)
        finally:
            self._restore_auth()

    # ------------------------------------------------------------------
    # POST /api/projects/{project_id}/managers
    # ------------------------------------------------------------------
    def test_add_manager_success(self, client):
        user_id = str(uuid4())
        project_id = str(uuid4())
        self._override_auth(user_id)
        try:
            mock_repo = AsyncMock(spec=ProjectRepository)
            mock_repo.get_project_by_id = AsyncMock(return_value={
                "id": project_id, "user_id": user_id
            })
            mock_repo.add_manager = AsyncMock()

            app.dependency_overrides[get_project_repo] = lambda: mock_repo

            payload = {"chat_id": 777}
            response = client.post(f"/api/projects/{project_id}/managers", json=payload)
            assert response.status_code == 201
            assert response.json() == {"status": "added"}

            mock_repo.add_manager.assert_awaited_once_with(project_id, "777")

            app.dependency_overrides.pop(get_project_repo, None)
        finally:
            self._restore_auth()

    def test_add_manager_invalid_chat_id(self, client):
        self._override_auth(str(uuid4()))
        try:
            payload = {"chat_id": "not_int"}
            response = client.post(f"/api/projects/{uuid4()}/managers", json=payload)
            assert response.status_code == 422
            errors = response.json()["detail"]
            assert any(err["loc"] == ["body", "chat_id"] for err in errors)
        finally:
            self._restore_auth()

    def test_add_manager_forbidden_no_project(self, client):
        user_id = str(uuid4())
        project_id = str(uuid4())
        self._override_auth(user_id)
        try:
            mock_repo = AsyncMock(spec=ProjectRepository)
            mock_repo.get_project_by_id = AsyncMock(return_value=None)

            app.dependency_overrides[get_project_repo] = lambda: mock_repo

            response = client.post(f"/api/projects/{project_id}/managers", json={"chat_id": 123})
            assert response.status_code == 403
            assert response.json()["detail"] == "Access denied"

            app.dependency_overrides.pop(get_project_repo, None)
        finally:
            self._restore_auth()

    def test_add_manager_forbidden_wrong_user(self, client):
        user_id = str(uuid4())
        other_user_id = str(uuid4())
        project_id = str(uuid4())
        self._override_auth(user_id)
        try:
            mock_repo = AsyncMock(spec=ProjectRepository)
            mock_repo.get_project_by_id = AsyncMock(return_value={
                "id": project_id, "user_id": other_user_id
            })

            app.dependency_overrides[get_project_repo] = lambda: mock_repo

            response = client.post(f"/api/projects/{project_id}/managers", json={"chat_id": 123})
            assert response.status_code == 403
            assert response.json()["detail"] == "Access denied"

            app.dependency_overrides.pop(get_project_repo, None)
        finally:
            self._restore_auth()

    # ------------------------------------------------------------------
    # DELETE /api/projects/{project_id}/managers/{chat_id}
    # ------------------------------------------------------------------
    def test_remove_manager_success(self, client):
        user_id = str(uuid4())
        project_id = str(uuid4())
        self._override_auth(user_id)
        try:
            mock_repo = AsyncMock(spec=ProjectRepository)
            mock_repo.get_project_by_id = AsyncMock(return_value={
                "id": project_id, "user_id": user_id
            })
            mock_repo.remove_manager = AsyncMock()

            app.dependency_overrides[get_project_repo] = lambda: mock_repo

            response = client.delete(f"/api/projects/{project_id}/managers/888")
            assert response.status_code == 204

            mock_repo.remove_manager.assert_awaited_once_with(project_id, "888")

            app.dependency_overrides.pop(get_project_repo, None)
        finally:
            self._restore_auth()

    def test_remove_manager_forbidden_no_project(self, client):
        user_id = str(uuid4())
        project_id = str(uuid4())
        self._override_auth(user_id)
        try:
            mock_repo = AsyncMock(spec=ProjectRepository)
            mock_repo.get_project_by_id = AsyncMock(return_value=None)

            app.dependency_overrides[get_project_repo] = lambda: mock_repo

            response = client.delete(f"/api/projects/{project_id}/managers/123")
            assert response.status_code == 403
            assert response.json()["detail"] == "Access denied"

            app.dependency_overrides.pop(get_project_repo, None)
        finally:
            self._restore_auth()

    def test_remove_manager_forbidden_wrong_user(self, client):
        user_id = str(uuid4())
        other_user_id = str(uuid4())
        project_id = str(uuid4())
        self._override_auth(user_id)
        try:
            mock_repo = AsyncMock(spec=ProjectRepository)
            mock_repo.get_project_by_id = AsyncMock(return_value={
                "id": project_id, "user_id": other_user_id
            })

            app.dependency_overrides[get_project_repo] = lambda: mock_repo

            response = client.delete(f"/api/projects/{project_id}/managers/123")
            assert response.status_code == 403
            assert response.json()["detail"] == "Access denied"

            app.dependency_overrides.pop(get_project_repo, None)
        finally:
            self._restore_auth()

    # ------------------------------------------------------------------
    # POST /api/projects/{project_id}/connect-bot
    # ------------------------------------------------------------------
    def test_connect_bot_client_success(self, client):
        user_id = str(uuid4())
        project_id = str(uuid4())
        self._override_auth(user_id)
        try:
            mock_repo = AsyncMock(spec=ProjectRepository)
            mock_repo.get_project_by_id = AsyncMock(return_value={
                "id": project_id, "user_id": user_id
            })
            mock_repo.set_bot_token = AsyncMock()
            mock_repo.set_manager_bot_token = AsyncMock()

            app.dependency_overrides[get_project_repo] = lambda: mock_repo

            payload = {"token": "client_token", "type": "client"}
            response = client.post(f"/api/projects/{project_id}/connect-bot", json=payload)
            assert response.status_code == 200
            assert response.json() == {"status": "ok", "type": "client"}

            mock_repo.set_bot_token.assert_awaited_once_with(project_id, "client_token")
            mock_repo.set_manager_bot_token.assert_not_called()

            app.dependency_overrides.pop(get_project_repo, None)
        finally:
            self._restore_auth()

    def test_connect_bot_manager_success(self, client):
        user_id = str(uuid4())
        project_id = str(uuid4())
        self._override_auth(user_id)
        try:
            mock_repo = AsyncMock(spec=ProjectRepository)
            mock_repo.get_project_by_id = AsyncMock(return_value={
                "id": project_id, "user_id": user_id
            })
            mock_repo.set_bot_token = AsyncMock()
            mock_repo.set_manager_bot_token = AsyncMock()

            app.dependency_overrides[get_project_repo] = lambda: mock_repo

            payload = {"token": "manager_token", "type": "manager"}
            response = client.post(f"/api/projects/{project_id}/connect-bot", json=payload)
            assert response.status_code == 200
            assert response.json() == {"status": "ok", "type": "manager"}

            mock_repo.set_manager_bot_token.assert_awaited_once_with(project_id, "manager_token")
            mock_repo.set_bot_token.assert_not_called()

            app.dependency_overrides.pop(get_project_repo, None)
        finally:
            self._restore_auth()

    def test_connect_bot_invalid_type(self, client):
        user_id = str(uuid4())
        project_id = str(uuid4())
        self._override_auth(user_id)
        try:
            mock_repo = AsyncMock(spec=ProjectRepository)
            mock_repo.get_project_by_id = AsyncMock(return_value={
                "id": project_id, "user_id": user_id
            })

            app.dependency_overrides[get_project_repo] = lambda: mock_repo

            payload = {"token": "token", "type": "invalid"}
            response = client.post(f"/api/projects/{project_id}/connect-bot", json=payload)
            assert response.status_code == 400
            assert response.json()["detail"] == "Invalid bot type"

            app.dependency_overrides.pop(get_project_repo, None)
        finally:
            self._restore_auth()

    def test_connect_bot_forbidden_no_project(self, client):
        user_id = str(uuid4())
        project_id = str(uuid4())
        self._override_auth(user_id)
        try:
            mock_repo = AsyncMock(spec=ProjectRepository)
            mock_repo.get_project_by_id = AsyncMock(return_value=None)

            app.dependency_overrides[get_project_repo] = lambda: mock_repo

            payload = {"token": "t", "type": "client"}
            response = client.post(f"/api/projects/{project_id}/connect-bot", json=payload)
            assert response.status_code == 403
            assert response.json()["detail"] == "Access denied"

            app.dependency_overrides.pop(get_project_repo, None)
        finally:
            self._restore_auth()

    def test_connect_bot_forbidden_wrong_user(self, client):
        user_id = str(uuid4())
        other_user_id = str(uuid4())
        project_id = str(uuid4())
        self._override_auth(user_id)
        try:
            mock_repo = AsyncMock(spec=ProjectRepository)
            mock_repo.get_project_by_id = AsyncMock(return_value={
                "id": project_id, "user_id": other_user_id
            })

            app.dependency_overrides[get_project_repo] = lambda: mock_repo

            payload = {"token": "t", "type": "client"}
            response = client.post(f"/api/projects/{project_id}/connect-bot", json=payload)
            assert response.status_code == 403
            assert response.json()["detail"] == "Access denied"

            app.dependency_overrides.pop(get_project_repo, None)
        finally:
            self._restore_auth()
