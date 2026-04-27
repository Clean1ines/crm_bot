import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from uuid import uuid4

from src.interfaces.http.app import app
from src.interfaces.http.dependencies import get_current_user_id, get_project_repo
from src.infrastructure.db.repositories.project import ProjectRepository
from src.domain.control_plane.project_views import ProjectSummaryView, ProjectMemberView
from src.domain.control_plane.project_configuration import ProjectConfigurationView, ProjectIntegrationView, ProjectChannelView


@pytest.fixture(autouse=True)
def mock_lifespan_pool():
    """Mock global pool to avoid RuntimeError."""
    with patch("src.interfaces.composition.fastapi_lifespan.pool", MagicMock()):
        yield


@pytest.fixture
def client():
    return TestClient(app)


def _project_view(project_id, user_id, name="Test Project", is_pro_mode=False):
    return ProjectSummaryView(
        id=str(project_id),
        user_id=str(user_id),
        name=name,
        is_pro_mode=is_pro_mode,
    )


def _project_config_view(project_id, settings=None, policies=None, limit_profile=None, integrations=None, channels=None):
    return ProjectConfigurationView(
        project_id=str(project_id),
        settings=settings or {},
        policies=policies or {},
        limit_profile=limit_profile or {},
        integrations=[
            item if isinstance(item, ProjectIntegrationView) else ProjectIntegrationView.from_record(item)
            for item in (integrations or [])
        ],
        channels=[
            item if isinstance(item, ProjectChannelView) else ProjectChannelView.from_record(item)
            for item in (channels or [])
        ],
        prompt_versions=[],
    )


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
            mock_repo.get_projects_for_user_view = AsyncMock(return_value=[
                ProjectSummaryView(
                    id=str(uuid4()),
                    name="Proj1",
                    is_pro_mode=False,
                    user_id=user_id,
                    client_bot_username=None,
                    manager_bot_username=None,
                    access_role="owner",
                ),
                ProjectSummaryView(
                    id=str(uuid4()),
                    name="Proj2",
                    is_pro_mode=True,
                    user_id=user_id,
                    client_bot_username="bot1",
                    manager_bot_username=None,
                    access_role="manager",
                ),
            ])
            original = app.dependency_overrides.get(get_project_repo)
            app.dependency_overrides[get_project_repo] = lambda: mock_repo

            response = client.get("/api/projects")
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2
            assert data[0]["name"] == "Proj1"
            assert data[1]["client_bot_username"] == "bot1"

            mock_repo.get_projects_for_user_view.assert_awaited_once_with(user_id)

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
            mock_repo.get_project_view = AsyncMock(return_value=_project_view(
                project_id, user_id, name="New Project", is_pro_mode=False
            ))
            app.dependency_overrides[get_project_repo] = lambda: mock_repo

            payload = {"name": "New Project"}
            response = client.post("/api/projects", json=payload)
            assert response.status_code == 201
            data = response.json()
            assert data["id"] == project_id
            assert data["name"] == "New Project"
            assert data["user_id"] == user_id

            mock_repo.create_project_with_user_id.assert_awaited_once_with(user_id, "New Project")
            mock_repo.get_project_view.assert_awaited_once_with(project_id)

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
            mock_repo.get_project_view = AsyncMock(return_value=None)

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
            mock_repo.get_project_view = AsyncMock(return_value=_project_view(
                project_id, user_id, name="Test", is_pro_mode=False
            ))
            app.dependency_overrides[get_project_repo] = lambda: mock_repo

            response = client.get(f"/api/projects/{project_id}")
            assert response.status_code == 200
            data = response.json()
            assert data["id"] == project_id

            mock_repo.get_project_view.assert_awaited_once_with(project_id)

            app.dependency_overrides.pop(get_project_repo, None)
        finally:
            self._restore_auth()

    def test_get_project_not_found(self, client):
        user_id = str(uuid4())
        project_id = str(uuid4())
        self._override_auth(user_id)
        try:
            mock_repo = AsyncMock(spec=ProjectRepository)
            mock_repo.get_project_view = AsyncMock(return_value=None)

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
            mock_repo.get_project_view = AsyncMock(return_value=_project_view(
                project_id, other_user_id, name="Test"
            ))

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
            # Первый вызов get_project_view для проверки владельца
            mock_repo.get_project_view = AsyncMock(side_effect=[
                _project_view(project_id, user_id, name="Old", is_pro_mode=False),
                _project_view(project_id, user_id, name="Updated", is_pro_mode=False),
            ])
            mock_repo.update_project = AsyncMock()

            app.dependency_overrides[get_project_repo] = lambda: mock_repo

            payload = {"name": "Updated"}
            response = client.put(f"/api/projects/{project_id}", json=payload)
            assert response.status_code == 200
            data = response.json()
            assert data["name"] == "Updated"

            mock_repo.project_exists.assert_awaited_once_with(project_id)
            mock_repo.update_project.assert_awaited_once_with(project_id, "Updated")

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
            mock_repo.get_project_view = AsyncMock(return_value=_project_view(project_id, other_user_id))

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
            mock_repo.get_project_view = AsyncMock(return_value=_project_view(project_id, user_id))
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
            mock_repo.get_project_view = AsyncMock(return_value=_project_view(project_id, other_user_id))

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
            mock_repo.get_project_view = AsyncMock(return_value=_project_view(project_id, user_id))
            mock_repo.set_bot_token = AsyncMock()
            mock_repo.upsert_project_channel = AsyncMock()

            app.dependency_overrides[get_project_repo] = lambda: mock_repo

            payload = {"token": "bot123:token"}
            response = client.post(f"/api/projects/{project_id}/bot-token", json=payload)
            assert response.status_code == 200
            assert response.json() == {"status": "ok"}

            mock_repo.set_bot_token.assert_awaited_once_with(project_id, "bot123:token")
            mock_repo.upsert_project_channel.assert_awaited_once_with(
                project_id,
                kind="client",
                provider="telegram",
                status="active",
                config_json={"token_configured": True},
            )

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
            mock_repo.get_project_view = AsyncMock(return_value=_project_view(project_id, other_user_id))

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
            mock_repo.get_project_view = AsyncMock(return_value=_project_view(project_id, user_id))
            mock_repo.set_manager_bot_token = AsyncMock()
            mock_repo.upsert_project_channel = AsyncMock()

            app.dependency_overrides[get_project_repo] = lambda: mock_repo

            payload = {"token": "man123:token"}
            response = client.post(f"/api/projects/{project_id}/manager-token", json=payload)
            assert response.status_code == 200
            assert response.json() == {"status": "ok"}

            mock_repo.set_manager_bot_token.assert_awaited_once_with(project_id, "man123:token")
            mock_repo.upsert_project_channel.assert_awaited_once_with(
                project_id,
                kind="manager",
                provider="telegram",
                status="active",
                config_json={"token_configured": True},
            )

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
            mock_repo.get_project_view = AsyncMock(return_value=_project_view(project_id, other_user_id))

            app.dependency_overrides[get_project_repo] = lambda: mock_repo

            response = client.post(f"/api/projects/{project_id}/manager-token", json={"token": "t"})
            assert response.status_code == 403
            assert response.json()["detail"] == "Access denied"

            app.dependency_overrides.pop(get_project_repo, None)
        finally:
            self._restore_auth()

    def test_set_manager_token_rejects_empty_token(self, client):
        user_id = str(uuid4())
        project_id = str(uuid4())
        self._override_auth(user_id)
        try:
            mock_repo = AsyncMock(spec=ProjectRepository)
            mock_repo.project_exists = AsyncMock(return_value=True)
            mock_repo.get_project_view = AsyncMock(return_value=_project_view(project_id, user_id))
            mock_repo.set_manager_bot_token = AsyncMock()
            mock_repo.upsert_project_channel = AsyncMock()

            app.dependency_overrides[get_project_repo] = lambda: mock_repo

            response = client.post(f"/api/projects/{project_id}/manager-token", json={"token": "   "})
            assert response.status_code == 400
            assert response.json()["detail"] == "Bot token is required"

            mock_repo.set_manager_bot_token.assert_not_awaited()
            mock_repo.upsert_project_channel.assert_not_awaited()

            app.dependency_overrides.pop(get_project_repo, None)
        finally:
            self._restore_auth()

    def test_clear_bot_token_success(self, client):
        user_id = str(uuid4())
        project_id = str(uuid4())
        self._override_auth(user_id)
        try:
            mock_repo = AsyncMock(spec=ProjectRepository)
            mock_repo.project_exists = AsyncMock(return_value=True)
            mock_repo.get_project_view = AsyncMock(return_value=_project_view(project_id, user_id))
            mock_repo.set_bot_token = AsyncMock()
            mock_repo.upsert_project_channel = AsyncMock()

            app.dependency_overrides[get_project_repo] = lambda: mock_repo

            response = client.delete(f"/api/projects/{project_id}/bot-token")
            assert response.status_code == 200
            assert response.json() == {"status": "ok", "type": "client"}

            mock_repo.set_bot_token.assert_awaited_once_with(project_id, None)
            mock_repo.upsert_project_channel.assert_awaited_once_with(
                project_id,
                kind="client",
                provider="telegram",
                status="disabled",
                config_json={"token_configured": False},
            )

            app.dependency_overrides.pop(get_project_repo, None)
        finally:
            self._restore_auth()

    def test_clear_manager_token_success(self, client):
        user_id = str(uuid4())
        project_id = str(uuid4())
        self._override_auth(user_id)
        try:
            mock_repo = AsyncMock(spec=ProjectRepository)
            mock_repo.project_exists = AsyncMock(return_value=True)
            mock_repo.get_project_view = AsyncMock(return_value=_project_view(project_id, user_id))
            mock_repo.set_manager_bot_token = AsyncMock()
            mock_repo.upsert_project_channel = AsyncMock()

            app.dependency_overrides[get_project_repo] = lambda: mock_repo

            response = client.delete(f"/api/projects/{project_id}/manager-token")
            assert response.status_code == 200
            assert response.json() == {"status": "ok", "type": "manager"}

            mock_repo.set_manager_bot_token.assert_awaited_once_with(project_id, None)
            mock_repo.upsert_project_channel.assert_awaited_once_with(
                project_id,
                kind="manager",
                provider="telegram",
                status="disabled",
                config_json={"token_configured": False},
            )

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
            mock_repo.get_project_view = AsyncMock(return_value=_project_view(project_id, user_id))
            mock_repo.get_manager_notification_targets = AsyncMock(return_value=["123", "456"])

            app.dependency_overrides[get_project_repo] = lambda: mock_repo

            response = client.get(f"/api/projects/{project_id}/managers")
            assert response.status_code == 200
            assert response.json() == [123, 456]

            mock_repo.get_manager_notification_targets.assert_awaited_once_with(project_id)

            app.dependency_overrides.pop(get_project_repo, None)
        finally:
            self._restore_auth()

    def test_get_managers_forbidden_no_project(self, client):
        user_id = str(uuid4())
        project_id = str(uuid4())
        self._override_auth(user_id)
        try:
            mock_repo = AsyncMock(spec=ProjectRepository)
            mock_repo.get_project_view = AsyncMock(return_value=None)

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
            mock_repo.get_project_view = AsyncMock(return_value=_project_view(project_id, other_user_id))

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
            mock_repo.get_project_view = AsyncMock(return_value=_project_view(project_id, user_id))
            mock_repo.add_manager_by_telegram_identity = AsyncMock(return_value={
                "status": "added",
                "storage": "project_members",
                "user_id": str(uuid4()),
                "role": "manager",
            })

            app.dependency_overrides[get_project_repo] = lambda: mock_repo

            payload = {"chat_id": 777}
            response = client.post(f"/api/projects/{project_id}/managers", json=payload)
            assert response.status_code == 201
            assert response.json()["status"] == "added"
            assert response.json()["storage"] == "project_members"

            mock_repo.add_manager_by_telegram_identity.assert_awaited_once_with(project_id, "777")

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
            mock_repo.get_project_view = AsyncMock(return_value=None)

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
            mock_repo.get_project_view = AsyncMock(return_value=_project_view(project_id, other_user_id))

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
            mock_repo.get_project_view = AsyncMock(return_value=_project_view(project_id, user_id))
            mock_repo.remove_manager_by_telegram_identity = AsyncMock()

            app.dependency_overrides[get_project_repo] = lambda: mock_repo

            response = client.delete(f"/api/projects/{project_id}/managers/888")
            assert response.status_code == 204

            mock_repo.remove_manager_by_telegram_identity.assert_awaited_once_with(project_id, "888")

            app.dependency_overrides.pop(get_project_repo, None)
        finally:
            self._restore_auth()

    def test_remove_manager_forbidden_no_project(self, client):
        user_id = str(uuid4())
        project_id = str(uuid4())
        self._override_auth(user_id)
        try:
            mock_repo = AsyncMock(spec=ProjectRepository)
            mock_repo.get_project_view = AsyncMock(return_value=None)

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
            mock_repo.get_project_view = AsyncMock(return_value=_project_view(project_id, other_user_id))

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
            mock_repo.get_project_view = AsyncMock(return_value=_project_view(project_id, user_id))
            mock_repo.set_bot_token = AsyncMock()
            mock_repo.set_manager_bot_token = AsyncMock()
            mock_repo.upsert_project_channel = AsyncMock()

            app.dependency_overrides[get_project_repo] = lambda: mock_repo

            payload = {"token": "client_token", "type": "client"}
            response = client.post(f"/api/projects/{project_id}/connect-bot", json=payload)
            assert response.status_code == 200
            assert response.json() == {"status": "ok", "type": "client"}

            mock_repo.set_bot_token.assert_awaited_once_with(project_id, "client_token")
            mock_repo.upsert_project_channel.assert_awaited_once_with(
                project_id,
                kind="client",
                provider="telegram",
                status="active",
                config_json={"token_configured": True},
            )
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
            mock_repo.get_project_view = AsyncMock(return_value=_project_view(project_id, user_id))
            mock_repo.set_bot_token = AsyncMock()
            mock_repo.set_manager_bot_token = AsyncMock()
            mock_repo.upsert_project_channel = AsyncMock()

            app.dependency_overrides[get_project_repo] = lambda: mock_repo

            payload = {"token": "manager_token", "type": "manager"}
            response = client.post(f"/api/projects/{project_id}/connect-bot", json=payload)
            assert response.status_code == 200
            assert response.json() == {"status": "ok", "type": "manager"}

            mock_repo.set_manager_bot_token.assert_awaited_once_with(project_id, "manager_token")
            mock_repo.upsert_project_channel.assert_awaited_once_with(
                project_id,
                kind="manager",
                provider="telegram",
                status="active",
                config_json={"token_configured": True},
            )
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
            mock_repo.get_project_view = AsyncMock(return_value=_project_view(project_id, user_id))

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
            mock_repo.get_project_view = AsyncMock(return_value=None)

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
            mock_repo.get_project_view = AsyncMock(return_value=_project_view(project_id, other_user_id))

            app.dependency_overrides[get_project_repo] = lambda: mock_repo

            payload = {"token": "t", "type": "client"}
            response = client.post(f"/api/projects/{project_id}/connect-bot", json=payload)
            assert response.status_code == 403
            assert response.json()["detail"] == "Access denied"

            app.dependency_overrides.pop(get_project_repo, None)
        finally:
            self._restore_auth()

    def test_list_project_members_success(self, client):
        user_id = str(uuid4())
        project_id = str(uuid4())
        self._override_auth(user_id)
        try:
            mock_repo = AsyncMock(spec=ProjectRepository)
            mock_repo.get_project_view = AsyncMock(return_value=_project_view(project_id, user_id))
            mock_repo.get_project_members_view = AsyncMock(return_value=[
                ProjectMemberView.from_record({"project_id": project_id, "user_id": user_id, "role": "owner", "username": "owner"}),
                ProjectMemberView.from_record({"project_id": project_id, "user_id": str(uuid4()), "role": "manager", "username": "manager"}),
            ])

            app.dependency_overrides[get_project_repo] = lambda: mock_repo

            response = client.get(f"/api/projects/{project_id}/members")
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 2
            assert data[0]["role"] == "owner"
            mock_repo.get_project_members_view.assert_awaited_once_with(project_id)

            app.dependency_overrides.pop(get_project_repo, None)
        finally:
            self._restore_auth()

    def test_upsert_project_member_success(self, client):
        user_id = str(uuid4())
        member_user_id = str(uuid4())
        project_id = str(uuid4())
        self._override_auth(user_id)
        try:
            mock_repo = AsyncMock(spec=ProjectRepository)
            mock_repo.get_project_view = AsyncMock(return_value=_project_view(project_id, user_id))
            mock_repo.add_project_member = AsyncMock()

            app.dependency_overrides[get_project_repo] = lambda: mock_repo

            response = client.post(f"/api/projects/{project_id}/members", json={
                "user_id": member_user_id,
                "role": "manager",
            })
            assert response.status_code == 201
            assert response.json() == {"status": "ok", "user_id": member_user_id, "role": "manager"}
            mock_repo.add_project_member.assert_awaited_once_with(project_id, member_user_id, "manager")

            app.dependency_overrides.pop(get_project_repo, None)
        finally:
            self._restore_auth()

    def test_upsert_project_member_rejects_unknown_role(self, client):
        user_id = str(uuid4())
        member_user_id = str(uuid4())
        project_id = str(uuid4())
        self._override_auth(user_id)
        try:
            mock_repo = AsyncMock(spec=ProjectRepository)
            mock_repo.get_project_view = AsyncMock(return_value=_project_view(project_id, user_id))
            mock_repo.add_project_member = AsyncMock()

            app.dependency_overrides[get_project_repo] = lambda: mock_repo

            response = client.post(f"/api/projects/{project_id}/members", json={
                "user_id": member_user_id,
                "role": "superuser",
            })
            assert response.status_code == 400
            assert response.json()["detail"] == "Invalid project role"
            mock_repo.add_project_member.assert_not_awaited()

            app.dependency_overrides.pop(get_project_repo, None)
        finally:
            self._restore_auth()

    def test_delete_project_member_success(self, client):
        user_id = str(uuid4())
        member_user_id = str(uuid4())
        project_id = str(uuid4())
        self._override_auth(user_id)
        try:
            mock_repo = AsyncMock(spec=ProjectRepository)
            mock_repo.get_project_view = AsyncMock(return_value=_project_view(project_id, user_id))
            mock_repo.remove_project_member = AsyncMock()

            app.dependency_overrides[get_project_repo] = lambda: mock_repo

            response = client.delete(f"/api/projects/{project_id}/members/{member_user_id}")
            assert response.status_code == 204
            mock_repo.remove_project_member.assert_awaited_once_with(project_id, member_user_id)

            app.dependency_overrides.pop(get_project_repo, None)
        finally:
            self._restore_auth()

    def test_get_project_configuration_view_success(self, client):
        user_id = str(uuid4())
        project_id = str(uuid4())
        self._override_auth(user_id)
        try:
            mock_repo = AsyncMock(spec=ProjectRepository)
            mock_repo.get_project_view = AsyncMock(return_value=_project_view(project_id, user_id))
            mock_repo.get_project_configuration_view = AsyncMock(return_value=_project_config_view(
                project_id,
                settings={"brand_name": "Acme"},
                policies={"escalation_policy_json": {"mode": "manual"}},
                limit_profile={},
                integrations=[],
                channels=[],
            ))

            app.dependency_overrides[get_project_repo] = lambda: mock_repo

            response = client.get(f"/api/projects/{project_id}/configuration")
            assert response.status_code == 200
            data = response.json()
            assert data["project_id"] == project_id
            assert data["settings"]["brand_name"] == "Acme"
            mock_repo.get_project_configuration_view.assert_awaited_once_with(project_id)

            app.dependency_overrides.pop(get_project_repo, None)
        finally:
            self._restore_auth()

    def test_update_project_settings_success(self, client):
        user_id = str(uuid4())
        project_id = str(uuid4())
        self._override_auth(user_id)
        try:
            mock_repo = AsyncMock(spec=ProjectRepository)
            mock_repo.get_project_view = AsyncMock(return_value=_project_view(project_id, user_id))
            mock_repo.update_project_settings = AsyncMock()
            mock_repo.get_project_configuration_view = AsyncMock(return_value=_project_config_view(
                project_id,
                settings={"brand_name": "Acme"},
                policies={},
                limit_profile={},
                integrations=[],
                channels=[],
            ))

            app.dependency_overrides[get_project_repo] = lambda: mock_repo

            response = client.patch(f"/api/projects/{project_id}/settings", json={"brand_name": "Acme"})
            assert response.status_code == 200
            assert response.json()["settings"]["brand_name"] == "Acme"
            mock_repo.update_project_settings.assert_awaited_once_with(project_id, {"brand_name": "Acme"})

            app.dependency_overrides.pop(get_project_repo, None)
        finally:
            self._restore_auth()

    def test_update_project_policies_success(self, client):
        user_id = str(uuid4())
        project_id = str(uuid4())
        self._override_auth(user_id)
        try:
            mock_repo = AsyncMock(spec=ProjectRepository)
            mock_repo.get_project_view = AsyncMock(return_value=_project_view(project_id, user_id))
            mock_repo.update_project_policies = AsyncMock()
            mock_repo.get_project_configuration_view = AsyncMock(return_value=_project_config_view(
                project_id,
                settings={},
                policies={"routing_policy_json": {"mode": "support"}},
                limit_profile={},
                integrations=[],
                channels=[],
            ))

            app.dependency_overrides[get_project_repo] = lambda: mock_repo

            response = client.patch(
                f"/api/projects/{project_id}/policies",
                json={"routing_policy_json": {"mode": "support"}},
            )
            assert response.status_code == 200
            assert response.json()["policies"]["routing_policy_json"]["mode"] == "support"
            mock_repo.update_project_policies.assert_awaited_once_with(
                project_id,
                {"routing_policy_json": {"mode": "support"}},
            )

            app.dependency_overrides.pop(get_project_repo, None)
        finally:
            self._restore_auth()

    def test_update_project_limits_success(self, client):
        user_id = str(uuid4())
        project_id = str(uuid4())
        self._override_auth(user_id)
        try:
            mock_repo = AsyncMock(spec=ProjectRepository)
            mock_repo.get_project_view = AsyncMock(return_value=_project_view(project_id, user_id))
            mock_repo.update_project_limit_profile = AsyncMock()
            mock_repo.get_project_configuration_view = AsyncMock(return_value=_project_config_view(
                project_id,
                settings={},
                policies={},
                limit_profile={"requests_per_minute": 30},
                integrations=[],
                channels=[],
            ))

            app.dependency_overrides[get_project_repo] = lambda: mock_repo

            response = client.patch(f"/api/projects/{project_id}/limits", json={"requests_per_minute": 30})
            assert response.status_code == 200
            assert response.json()["limit_profile"]["requests_per_minute"] == 30
            mock_repo.update_project_limit_profile.assert_awaited_once_with(
                project_id,
                {"requests_per_minute": 30},
            )

            app.dependency_overrides.pop(get_project_repo, None)
        finally:
            self._restore_auth()

    def test_list_project_integrations_success(self, client):
        user_id = str(uuid4())
        project_id = str(uuid4())
        self._override_auth(user_id)
        try:
            mock_repo = AsyncMock(spec=ProjectRepository)
            mock_repo.get_project_view = AsyncMock(return_value=_project_view(project_id, user_id))
            mock_repo.get_project_configuration_view = AsyncMock(return_value=_project_config_view(
                project_id,
                settings={},
                policies={},
                limit_profile={},
                integrations=[{"provider": "custom_webhook", "status": "enabled"}],
                channels=[],
            ))

            app.dependency_overrides[get_project_repo] = lambda: mock_repo

            response = client.get(f"/api/projects/{project_id}/integrations")
            assert response.status_code == 200
            assert response.json() == [{"provider": "custom_webhook", "status": "enabled"}]

            app.dependency_overrides.pop(get_project_repo, None)
        finally:
            self._restore_auth()

    def test_upsert_project_integration_success(self, client):
        user_id = str(uuid4())
        project_id = str(uuid4())
        self._override_auth(user_id)
        try:
            mock_repo = AsyncMock(spec=ProjectRepository)
            mock_repo.get_project_view = AsyncMock(return_value=_project_view(project_id, user_id))
            mock_repo.upsert_project_integration = AsyncMock(return_value=ProjectIntegrationView(
                id=str(uuid4()),
                project_id=project_id,
                provider="custom_webhook",
                status="enabled",
                config_json={"url": "https://example.com/hook"},
            ))

            app.dependency_overrides[get_project_repo] = lambda: mock_repo

            response = client.post(f"/api/projects/{project_id}/integrations", json={
                "provider": "custom_webhook",
                "status": "enabled",
                "config_json": {"url": "https://example.com/hook"},
            })
            assert response.status_code == 201
            assert response.json()["provider"] == "custom_webhook"
            mock_repo.upsert_project_integration.assert_awaited_once_with(
                project_id,
                provider="custom_webhook",
                status="enabled",
                config_json={"url": "https://example.com/hook"},
                credentials_encrypted=None,
            )

            app.dependency_overrides.pop(get_project_repo, None)
        finally:
            self._restore_auth()

    def test_upsert_project_integration_rejects_empty_provider(self, client):
        user_id = str(uuid4())
        project_id = str(uuid4())
        self._override_auth(user_id)
        try:
            mock_repo = AsyncMock(spec=ProjectRepository)
            mock_repo.get_project_view = AsyncMock(return_value=_project_view(project_id, user_id))
            mock_repo.upsert_project_integration = AsyncMock()

            app.dependency_overrides[get_project_repo] = lambda: mock_repo

            response = client.post(f"/api/projects/{project_id}/integrations", json={
                "provider": " ",
                "status": "enabled",
            })
            assert response.status_code == 400
            assert response.json()["detail"] == "Integration provider is required"
            mock_repo.upsert_project_integration.assert_not_awaited()

            app.dependency_overrides.pop(get_project_repo, None)
        finally:
            self._restore_auth()

    def test_list_project_channels_success(self, client):
        user_id = str(uuid4())
        project_id = str(uuid4())
        self._override_auth(user_id)
        try:
            mock_repo = AsyncMock(spec=ProjectRepository)
            mock_repo.get_project_view = AsyncMock(return_value=_project_view(project_id, user_id))
            mock_repo.get_project_configuration_view = AsyncMock(return_value=_project_config_view(
                project_id,
                settings={},
                policies={},
                limit_profile={},
                integrations=[],
                channels=[{"kind": "widget", "provider": "web", "status": "active"}],
            ))

            app.dependency_overrides[get_project_repo] = lambda: mock_repo

            response = client.get(f"/api/projects/{project_id}/channels")
            assert response.status_code == 200
            assert response.json() == [{"kind": "widget", "provider": "web", "status": "active"}]

            app.dependency_overrides.pop(get_project_repo, None)
        finally:
            self._restore_auth()

    def test_upsert_project_channel_success(self, client):
        user_id = str(uuid4())
        project_id = str(uuid4())
        self._override_auth(user_id)
        try:
            mock_repo = AsyncMock(spec=ProjectRepository)
            mock_repo.get_project_view = AsyncMock(return_value=_project_view(project_id, user_id))
            mock_repo.upsert_project_channel = AsyncMock(return_value=ProjectChannelView(
                id=str(uuid4()),
                project_id=project_id,
                kind="widget",
                provider="web",
                status="active",
                config_json={"allowed_origin": "https://site.example"},
            ))

            app.dependency_overrides[get_project_repo] = lambda: mock_repo

            response = client.post(f"/api/projects/{project_id}/channels", json={
                "kind": "widget",
                "provider": "web",
                "status": "active",
                "config_json": {"allowed_origin": "https://site.example"},
            })
            assert response.status_code == 201
            assert response.json()["kind"] == "widget"
            mock_repo.upsert_project_channel.assert_awaited_once_with(
                project_id,
                kind="widget",
                provider="web",
                status="active",
                config_json={"allowed_origin": "https://site.example"},
            )

            app.dependency_overrides.pop(get_project_repo, None)
        finally:
            self._restore_auth()

    def test_project_configuration_openapi_contract_is_typed(self):
        schema = app.openapi()
        paths = schema["paths"]

        assert paths["/api/projects/{project_id}/configuration"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith("/ProjectConfigurationResponse")
        assert paths["/api/projects/{project_id}/settings"]["patch"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith("/ProjectConfigurationResponse")
        assert paths["/api/projects/{project_id}/policies"]["patch"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith("/ProjectConfigurationResponse")
        assert paths["/api/projects/{project_id}/limits"]["patch"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith("/ProjectConfigurationResponse")

        integrations_schema = paths["/api/projects/{project_id}/integrations"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
        assert integrations_schema["items"]["$ref"].endswith("/ProjectIntegrationResponse")
        assert paths["/api/projects/{project_id}/integrations"]["post"]["responses"]["201"]["content"]["application/json"]["schema"]["$ref"].endswith("/ProjectIntegrationResponse")

        channels_schema = paths["/api/projects/{project_id}/channels"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
        assert channels_schema["items"]["$ref"].endswith("/ProjectChannelResponse")
        assert paths["/api/projects/{project_id}/channels"]["post"]["responses"]["201"]["content"]["application/json"]["schema"]["$ref"].endswith("/ProjectChannelResponse")

    def test_upsert_project_channel_rejects_invalid_kind(self, client):
        user_id = str(uuid4())
        project_id = str(uuid4())
        self._override_auth(user_id)
        try:
            mock_repo = AsyncMock(spec=ProjectRepository)
            mock_repo.get_project_view = AsyncMock(return_value=_project_view(project_id, user_id))
            mock_repo.upsert_project_channel = AsyncMock()

            app.dependency_overrides[get_project_repo] = lambda: mock_repo

            response = client.post(f"/api/projects/{project_id}/channels", json={
                "kind": "telegram",
                "provider": "web",
                "status": "active",
            })
            assert response.status_code == 400
            assert response.json()["detail"] == "Invalid channel kind"
            mock_repo.upsert_project_channel.assert_not_awaited()

            app.dependency_overrides.pop(get_project_repo, None)
        finally:
            self._restore_auth()
