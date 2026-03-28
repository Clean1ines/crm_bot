import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from uuid import uuid4

from src.main import app
from src.api.dependencies import get_pool, get_orchestrator, get_project_repo


@pytest.fixture(autouse=True)
def mock_lifespan_pool():
    """Мокаем глобальный пул соединений, чтобы избежать RuntimeError."""
    with patch("src.core.lifespan.pool", MagicMock()):
        yield


@pytest.fixture(autouse=True)
def mock_dependencies():
    """
    Мокаем get_pool и get_orchestrator для всех тестов.
    Это необходимо, потому что зависимости вычисляются до тела функции,
    даже если в коде они не используются (например, при 401).
    """
    mock_pool = MagicMock()
    mock_orchestrator = MagicMock()
    app.dependency_overrides[get_pool] = lambda: mock_pool
    app.dependency_overrides[get_orchestrator] = lambda: mock_orchestrator
    yield
    # Очистка будет выполнена в reset_dependency_overrides


@pytest.fixture(autouse=True)
def reset_dependency_overrides():
    """После каждого теста сбрасываем переопределения зависимостей."""
    original_overrides = app.dependency_overrides.copy()
    yield
    app.dependency_overrides.clear()
    app.dependency_overrides.update(original_overrides)


@pytest.fixture
def client():
    return TestClient(app)


class TestWebhooks:
    # ------------------------------------------------------------------
    # POST /webhook/{project_id}
    # ------------------------------------------------------------------
    def test_webhook_client_success(self, client):
        """Успешный вызов с bot_token != ADMIN_BOT_TOKEN → process_client_update."""
        project_id = str(uuid4())
        secret_token = "valid-secret"
        bot_token = "client_bot_token"
        update = {"update_id": 12345, "message": {"chat": {"id": 111}, "text": "Hello"}}
        expected_update = update.copy()
        expected_update["_bot_token"] = bot_token

        mock_project_repo = AsyncMock()
        mock_project_repo.get_webhook_secret = AsyncMock(return_value=secret_token)
        mock_project_repo.get_bot_token = AsyncMock(return_value=bot_token)

        app.dependency_overrides[get_project_repo] = lambda: mock_project_repo

        with patch("src.api.webhooks.process_client_update", new_callable=AsyncMock) as mock_process_client:
            mock_process_client.return_value = {"ok": True}
            with patch("src.core.config.settings.ADMIN_BOT_TOKEN", "admin_token"):
                response = client.post(
                    f"/webhook/{project_id}",
                    json=update,
                    headers={"X-Telegram-Bot-Api-Secret-Token": secret_token}
                )

        assert response.status_code == 200
        assert response.json() == {"ok": True}
        mock_process_client.assert_awaited_once_with(
            expected_update, project_id, app.dependency_overrides[get_orchestrator](), bot_token
        )

    def test_webhook_admin_success(self, client):
        """Успешный вызов с bot_token == ADMIN_BOT_TOKEN → process_admin_update."""
        project_id = str(uuid4())
        secret_token = "valid-secret"
        admin_token = "admin_token"
        update = {"update_id": 12345, "message": {"chat": {"id": 111}, "text": "/start"}}
        expected_update = update.copy()
        expected_update["_bot_token"] = admin_token

        mock_project_repo = AsyncMock()
        mock_project_repo.get_webhook_secret = AsyncMock(return_value=secret_token)
        mock_project_repo.get_bot_token = AsyncMock(return_value=admin_token)

        app.dependency_overrides[get_project_repo] = lambda: mock_project_repo

        with patch("src.api.webhooks.process_admin_update", new_callable=AsyncMock) as mock_process_admin:
            mock_process_admin.return_value = {"ok": True}
            with patch("src.core.config.settings.ADMIN_BOT_TOKEN", admin_token):
                response = client.post(
                    f"/webhook/{project_id}",
                    json=update,
                    headers={"X-Telegram-Bot-Api-Secret-Token": secret_token}
                )

        assert response.status_code == 200
        assert response.json() == {"ok": True}
        mock_process_admin.assert_awaited_once_with(expected_update, app.dependency_overrides[get_pool]())

    def test_webhook_missing_secret_token(self, client):
        """Отсутствует заголовок X-Telegram-Bot-Api-Secret-Token → 401."""
        project_id = str(uuid4())
        response = client.post(f"/webhook/{project_id}", json={})
        assert response.status_code == 401
        assert response.json()["detail"] == "Missing secret token"

    def test_webhook_invalid_secret_token(self, client):
        """Неверный secret_token → 401."""
        project_id = str(uuid4())
        secret_token = "valid-secret"
        wrong_token = "wrong"

        mock_project_repo = AsyncMock()
        mock_project_repo.get_webhook_secret = AsyncMock(return_value=secret_token)
        # bot_token не важен для этого теста, но метод должен быть, чтобы не было ошибки
        mock_project_repo.get_bot_token = AsyncMock(return_value="some_token")
        app.dependency_overrides[get_project_repo] = lambda: mock_project_repo

        response = client.post(
            f"/webhook/{project_id}",
            json={"update_id": 1},
            headers={"X-Telegram-Bot-Api-Secret-Token": wrong_token}
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid secret token"

    def test_webhook_project_not_found(self, client):
        """Проект не найден (нет bot_token) → 404."""
        project_id = str(uuid4())
        secret_token = "valid-secret"
        mock_project_repo = AsyncMock()
        mock_project_repo.get_webhook_secret = AsyncMock(return_value=secret_token)
        mock_project_repo.get_bot_token = AsyncMock(return_value=None)

        app.dependency_overrides[get_project_repo] = lambda: mock_project_repo

        response = client.post(
            f"/webhook/{project_id}",
            json={},
            headers={"X-Telegram-Bot-Api-Secret-Token": secret_token}
        )
        assert response.status_code == 404
        assert response.json()["detail"] == "Project not found"

    # ------------------------------------------------------------------
    # POST /manager/webhook
    # ------------------------------------------------------------------
    def test_manager_webhook_success(self, client):
        """Успешный вызов с валидным secret_token и chat_id в списке менеджеров."""
        secret_token = "manager-secret"
        project_id = str(uuid4())
        manager_chat_id = 12345
        manager_bot_token = "manager_bot_token"
        update = {"message": {"from": {"id": manager_chat_id}, "chat": {"id": manager_chat_id}, "text": "reply"}}
        expected_update = update.copy()
        expected_update["_bot_token"] = manager_bot_token

        with patch("src.api.webhooks.ProjectRepository") as MockProjectRepo:
            mock_repo = AsyncMock()
            mock_repo.find_project_by_manager_webhook_secret = AsyncMock(return_value=project_id)
            mock_repo.get_manager_bot_token = AsyncMock(return_value=manager_bot_token)
            mock_repo.get_managers = AsyncMock(return_value=[str(manager_chat_id)])
            MockProjectRepo.return_value = mock_repo

            with patch("src.api.webhooks.process_manager_update", new_callable=AsyncMock) as mock_process_manager:
                mock_process_manager.return_value = {"ok": True}

                with patch("src.managers.router.get_redis_client", new_callable=AsyncMock) as mock_redis_client:
                    mock_redis_client.return_value = AsyncMock()

                    with patch("httpx.AsyncClient") as MockAsyncClient:
                        mock_http_client = AsyncMock()
                        MockAsyncClient.return_value.__aenter__.return_value = mock_http_client

                        response = client.post(
                            "/manager/webhook",
                            json=update,
                            headers={"X-Telegram-Bot-Api-Secret-Token": secret_token}
                        )

        assert response.status_code == 200
        assert response.json() == {"ok": True}
        mock_process_manager.assert_awaited_once_with(
            expected_update, project_id, app.dependency_overrides[get_orchestrator](), manager_bot_token
        )
        mock_http_client.post.assert_not_called()

    def test_manager_webhook_missing_secret_token(self, client):
        """Отсутствует заголовок X-Telegram-Bot-Api-Secret-Token → 401."""
        response = client.post("/manager/webhook", json={})
        assert response.status_code == 401
        assert response.json()["detail"] == "Missing secret token"

    def test_manager_webhook_invalid_secret_token(self, client):
        """Неверный secret_token (не найден в БД) → 401."""
        secret_token = "wrong"
        with patch("src.api.webhooks.ProjectRepository") as MockProjectRepo:
            mock_repo = AsyncMock()
            mock_repo.find_project_by_manager_webhook_secret = AsyncMock(return_value=None)
            MockProjectRepo.return_value = mock_repo

            response = client.post(
                "/manager/webhook",
                json={},
                headers={"X-Telegram-Bot-Api-Secret-Token": secret_token}
            )
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid secret token"

    def test_manager_webhook_missing_manager_token(self, client):
        """Проект найден, но manager_bot_token отсутствует → 500."""
        secret_token = "manager-secret"
        project_id = str(uuid4())
        with patch("src.api.webhooks.ProjectRepository") as MockProjectRepo:
            mock_repo = AsyncMock()
            mock_repo.find_project_by_manager_webhook_secret = AsyncMock(return_value=project_id)
            mock_repo.get_manager_bot_token = AsyncMock(return_value=None)
            MockProjectRepo.return_value = mock_repo

            response = client.post(
                "/manager/webhook",
                json={},
                headers={"X-Telegram-Bot-Api-Secret-Token": secret_token}
            )
        assert response.status_code == 500
        assert response.json()["detail"] == "Manager token error"

    def test_manager_webhook_unauthorized_chat_id(self, client):
        """Chat_id не в списке менеджеров → отправляется сообщение о запрете, возвращается 200."""
        secret_token = "manager-secret"
        project_id = str(uuid4())
        manager_chat_id = 12345
        manager_bot_token = "manager_bot_token"
        update = {"message": {"from": {"id": manager_chat_id}, "chat": {"id": manager_chat_id}, "text": "hi"}}

        with patch("src.api.webhooks.ProjectRepository") as MockProjectRepo:
            mock_repo = AsyncMock()
            mock_repo.find_project_by_manager_webhook_secret = AsyncMock(return_value=project_id)
            mock_repo.get_manager_bot_token = AsyncMock(return_value=manager_bot_token)
            mock_repo.get_managers = AsyncMock(return_value=["99999"])
            MockProjectRepo.return_value = mock_repo

            # Мокаем отправку сообщения через httpx
            with patch("httpx.AsyncClient") as MockAsyncClient:
                mock_http_client = AsyncMock()
                MockAsyncClient.return_value.__aenter__.return_value = mock_http_client

                response = client.post(
                    "/manager/webhook",
                    json=update,
                    headers={"X-Telegram-Bot-Api-Secret-Token": secret_token}
                )

        assert response.status_code == 200
        assert response.json() == {"ok": True}
        mock_http_client.post.assert_awaited_once_with(
            f"https://api.telegram.org/bot{manager_bot_token}/sendMessage",
            json={"chat_id": manager_chat_id, "text": "⛔ Доступ запрещён. Вы не являетесь менеджером этого проекта."}
        )
        # Обработчик process_manager_update НЕ должен вызываться
        with patch("src.managers.router.process_manager_update", new_callable=AsyncMock) as mock_process_manager:
            mock_process_manager.assert_not_called()

    def test_manager_webhook_no_chat_id(self, client):
        """В update нет chat_id (ни message, ни callback_query) → возвращается 200 без вызова process_manager_update."""
        secret_token = "manager-secret"
        project_id = str(uuid4())
        update = {}

        with patch("src.api.webhooks.ProjectRepository") as MockProjectRepo:
            mock_repo = AsyncMock()
            mock_repo.find_project_by_manager_webhook_secret = AsyncMock(return_value=project_id)
            mock_repo.get_manager_bot_token = AsyncMock(return_value="token")
            MockProjectRepo.return_value = mock_repo

            with patch("src.managers.router.process_manager_update", new_callable=AsyncMock) as mock_process_manager:
                response = client.post(
                    "/manager/webhook",
                    json=update,
                    headers={"X-Telegram-Bot-Api-Secret-Token": secret_token}
                )
                assert response.status_code == 200
                assert response.json() == {"ok": True}
                mock_process_manager.assert_not_called()