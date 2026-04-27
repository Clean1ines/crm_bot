import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from uuid import uuid4

from src.domain.project_plane.client_views import (
    ClientDetailView,
    ClientListItemView,
    ClientListView,
)
from src.domain.project_plane.memory_views import MemoryEntryView
from src.interfaces.http.app import app
from src.interfaces.http.dependencies import (
    get_current_user_id,
    get_thread_read_repo,
    get_client_repo,
    get_project_repo,
    get_memory_repository,
)


@pytest.fixture
def mock_current_user_id():
    return "test-user-id"


@pytest.fixture
def mock_project_repo():
    repo = AsyncMock()
    return repo


@pytest.fixture
def mock_memory_repo():
    repo = AsyncMock()
    return repo


@pytest.fixture
def mock_thread_repo():
    repo = AsyncMock()
    repo.get_dialogs = AsyncMock()
    return repo


@pytest.fixture
def mock_client_repo():
    return AsyncMock()


@pytest.fixture(autouse=True)
def override_dependencies(
    mock_current_user_id,
    mock_project_repo,
    mock_thread_repo,
    mock_client_repo,
    mock_memory_repo,
):
    # Save original overrides
    original_overrides = app.dependency_overrides.copy()

    # Override dependencies
    app.dependency_overrides[get_current_user_id] = lambda: mock_current_user_id
    app.dependency_overrides[get_project_repo] = lambda: mock_project_repo
    app.dependency_overrides[get_thread_read_repo] = lambda: mock_thread_repo
    app.dependency_overrides[get_client_repo] = lambda: mock_client_repo
    app.dependency_overrides[get_memory_repository] = lambda: mock_memory_repo

    yield

    # Restore original overrides
    app.dependency_overrides.clear()
    app.dependency_overrides.update(original_overrides)


@pytest.fixture(autouse=True)
def mock_lifespan():
    with patch("asyncpg.create_pool") as mock_pool:
        mock_pool.return_value = AsyncMock()
        yield


@pytest.fixture
def client():
    return TestClient(app)


class TestClientsAPI:
    """Тесты для эндпоинтов /api/clients"""

    # ==================== GET /api/clients ====================

    def test_list_clients_success(self, client, mock_project_repo, mock_client_repo):
        project_id = str(uuid4())
        mock_project_repo.user_has_project_role = AsyncMock(return_value=True)

        client_id = str(uuid4())
        mock_client_repo.list_for_project_view.return_value = ClientListView(
            clients=[
                ClientListItemView(
                    id=client_id,
                    username="client1",
                    full_name="Client One",
                    chat_id=12345,
                    source="telegram",
                    created_at="2025-01-01T00:00:00",
                )
            ],
            total_clients=1,
            new_clients_7d=1,
            active_dialogs=0,
        )

        response = client.get(f"/api/clients?project_id={project_id}&limit=10&offset=0")

        assert response.status_code == 200
        data = response.json()
        assert "clients" in data
        assert len(data["clients"]) == 1
        client_data = data["clients"][0]
        assert client_data["username"] == "client1"
        assert client_data["full_name"] == "Client One"
        mock_client_repo.list_for_project_view.assert_awaited_once_with(
            project_id,
            limit=10,
            offset=0,
            search=None,
        )

    def test_list_clients_forbidden_project_not_found(self, client, mock_project_repo):
        mock_project_repo.user_has_project_role = AsyncMock(return_value=False)
        mock_project_repo.get_project_view = AsyncMock(return_value=None)
        project_id = str(uuid4())
        response = client.get(f"/api/clients?project_id={project_id}")
        assert response.status_code == 403
        assert response.json()["detail"] == "Access denied"

    def test_list_clients_forbidden_wrong_user(self, client, mock_project_repo):
        project_id = str(uuid4())
        mock_project_repo.user_has_project_role = AsyncMock(return_value=False)
        mock_project_repo.get_project_view = AsyncMock(return_value=None)
        response = client.get(f"/api/clients?project_id={project_id}")
        assert response.status_code == 403
        assert response.json()["detail"] == "Access denied"

    def test_list_clients_limit_out_of_range_low(self, client):
        project_id = str(uuid4())
        response = client.get(f"/api/clients?project_id={project_id}&limit=0")
        assert response.status_code == 422
        errors = response.json()["detail"]
        assert any(err["loc"] == ["query", "limit"] for err in errors)

    def test_list_clients_limit_out_of_range_high(self, client):
        project_id = str(uuid4())
        response = client.get(f"/api/clients?project_id={project_id}&limit=101")
        assert response.status_code == 422
        errors = response.json()["detail"]
        assert any(err["loc"] == ["query", "limit"] for err in errors)

    def test_list_clients_offset_negative(self, client):
        project_id = str(uuid4())
        response = client.get(f"/api/clients?project_id={project_id}&offset=-1")
        assert response.status_code == 422
        errors = response.json()["detail"]
        assert any(err["loc"] == ["query", "offset"] for err in errors)

    def test_list_clients_missing_project_id(self, client):
        response = client.get("/api/clients")
        assert response.status_code == 422
        errors = response.json()["detail"]
        assert any(err["loc"] == ["query", "project_id"] for err in errors)

    # ==================== GET /api/clients/{client_id} ====================

    def test_get_client_success(
        self,
        client,
        mock_project_repo,
        mock_client_repo,
        mock_thread_repo,
        mock_memory_repo,
    ):
        project_id = str(uuid4())
        client_id = str(uuid4())
        mock_project_repo.user_has_project_role = AsyncMock(return_value=True)

        mock_client_repo.get_by_id_view.return_value = ClientDetailView(
            id=client_id,
            username="client1",
            full_name="Client One",
            chat_id=12345,
            source="telegram",
            created_at="2025-01-01T00:00:00",
        )

        # Mock memory and threads
        mock_memory_repo.get_for_user_view.return_value = [
            MemoryEntryView(
                id=str(uuid4()), key="preference", value="test", type="user_edited"
            )
        ]
        mock_thread_repo.get_dialogs.return_value = [{"thread_id": "thread-1"}]

        response = client.get(f"/api/clients/{client_id}?project_id={project_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == client_id
        assert data["username"] == "client1"
        assert "memory" in data
        assert "threads" in data
        mock_memory_repo.get_for_user_view.assert_called_once_with(
            project_id, client_id, limit=100
        )
        mock_thread_repo.get_dialogs.assert_called_once_with(
            project_id, client_id=client_id
        )

    def test_get_client_forbidden_project_not_found(self, client, mock_project_repo):
        mock_project_repo.user_has_project_role = AsyncMock(return_value=False)
        mock_project_repo.get_project_view = AsyncMock(return_value=None)
        project_id = str(uuid4())
        client_id = str(uuid4())
        response = client.get(f"/api/clients/{client_id}?project_id={project_id}")
        assert response.status_code == 403
        assert response.json()["detail"] == "Access denied"

    def test_get_client_forbidden_wrong_user(self, client, mock_project_repo):
        project_id = str(uuid4())
        client_id = str(uuid4())
        mock_project_repo.user_has_project_role = AsyncMock(return_value=False)
        mock_project_repo.get_project_view = AsyncMock(return_value=None)
        response = client.get(f"/api/clients/{client_id}?project_id={project_id}")
        assert response.status_code == 403
        assert response.json()["detail"] == "Access denied"

    def test_get_client_not_found(self, client, mock_project_repo, mock_client_repo):
        project_id = str(uuid4())
        client_id = str(uuid4())
        mock_project_repo.user_has_project_role = AsyncMock(return_value=True)

        mock_client_repo.get_by_id_view.return_value = None

        response = client.get(f"/api/clients/{client_id}?project_id={project_id}")
        assert response.status_code == 404
        assert response.json()["detail"] == "Client not found"

    def test_get_client_missing_project_id(self, client):
        client_id = str(uuid4())
        response = client.get(f"/api/clients/{client_id}")
        assert response.status_code == 422
        errors = response.json()["detail"]
        assert any(err["loc"] == ["query", "project_id"] for err in errors)
