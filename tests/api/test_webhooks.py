import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from uuid import uuid4

from src.interfaces.http.app import app
from src.interfaces.http.dependencies import get_pool, get_orchestrator


@pytest.fixture(autouse=True)
def reset_dependency_overrides():
    original = app.dependency_overrides.copy()
    yield
    app.dependency_overrides.clear()
    app.dependency_overrides.update(original)


@pytest.fixture(autouse=True)
def mock_dependencies():
    mock_pool = MagicMock()
    mock_orchestrator = MagicMock()
    app.dependency_overrides[get_pool] = lambda: mock_pool
    app.dependency_overrides[get_orchestrator] = lambda: mock_orchestrator
    yield


@pytest.fixture
def client():
    return TestClient(app)


class TestWebhooks:
    def test_explicit_client_webhook_success(self, client):
        project_id = str(uuid4())
        secret_token = "valid-secret"
        bot_token = "client_bot_token"
        update = {"update_id": 12345, "message": {"chat": {"id": 111}, "text": "Hello"}}
        expected_update = update.copy()
        expected_update["_bot_token"] = bot_token

        with patch("src.interfaces.http.webhooks.ProjectTokenRepository") as MockTokens:
            tokens = AsyncMock()
            tokens.get_webhook_secret = AsyncMock(return_value=secret_token)
            tokens.get_bot_token = AsyncMock(return_value=bot_token)
            MockTokens.return_value = tokens

            with patch("src.interfaces.http.webhooks.process_client_update", new_callable=AsyncMock) as process:
                process.return_value = {"ok": True}
                response = client.post(
                    f"/webhooks/projects/{project_id}/client",
                    json=update,
                    headers={"X-Telegram-Bot-Api-Secret-Token": secret_token},
                )

        assert response.status_code == 200
        assert response.json() == {"ok": True}
        process.assert_awaited_once_with(
            expected_update,
            project_id,
            app.dependency_overrides[get_orchestrator](),
            bot_token,
        )

    def test_explicit_platform_webhook_success(self, client):
        secret_token = "platform-secret"
        admin_token = "admin_token"
        update = {"update_id": 12345, "message": {"chat": {"id": 111}, "text": "/start"}}
        expected_update = update.copy()
        expected_update["_bot_token"] = admin_token

        with patch("src.interfaces.http.webhooks.settings.ADMIN_BOT_TOKEN", admin_token):
            with patch("src.interfaces.http.webhooks.settings.PLATFORM_WEBHOOK_SECRET", secret_token):
                with patch("src.interfaces.http.webhooks.process_admin_update", new_callable=AsyncMock) as process:
                    process.return_value = {"ok": True}
                    response = client.post(
                        "/webhooks/platform",
                        json=update,
                        headers={"X-Telegram-Bot-Api-Secret-Token": secret_token},
                    )

        assert response.status_code == 200
        assert response.json() == {"ok": True}
        process.assert_awaited_once_with(expected_update, app.dependency_overrides[get_pool]())

    def test_explicit_manager_webhook_success(self, client):
        project_id = str(uuid4())
        secret_token = "manager-secret"
        manager_chat_id = 12345
        manager_bot_token = "manager_bot_token"
        update = {"message": {"from": {"id": manager_chat_id}, "chat": {"id": manager_chat_id}, "text": "reply"}}
        expected_update = update.copy()
        expected_update["_bot_token"] = manager_bot_token
        expected_update["_manager_user_id"] = "11111111-1111-1111-1111-111111111111"

        with patch("src.interfaces.http.webhooks.ProjectTokenRepository") as MockTokens:
            with patch("src.interfaces.http.webhooks.ProjectMemberRepository") as MockMembers:
                tokens = AsyncMock()
                tokens.get_manager_webhook_secret = AsyncMock(return_value=secret_token)
                tokens.get_manager_bot_token = AsyncMock(return_value=manager_bot_token)
                MockTokens.return_value = tokens

                members = AsyncMock()
                members.get_manager_notification_targets = AsyncMock(return_value=[str(manager_chat_id)])
                members.resolve_manager_user_id_by_telegram = AsyncMock(return_value="11111111-1111-1111-1111-111111111111")
                MockMembers.return_value = members

                with patch("src.interfaces.http.webhooks.process_manager_update", new_callable=AsyncMock) as process:
                    process.return_value = {"ok": True}
                    response = client.post(
                        f"/webhooks/projects/{project_id}/manager",
                        json=update,
                        headers={"X-Telegram-Bot-Api-Secret-Token": secret_token},
                    )

        assert response.status_code == 200
        assert response.json() == {"ok": True}
        process.assert_awaited_once_with(
            expected_update,
            project_id,
            app.dependency_overrides[get_orchestrator](),
            manager_bot_token,
        )

    def test_explicit_manager_webhook_success_via_membership_notification_target(self, client):
        self.test_explicit_manager_webhook_success(client)

    def test_webhook_client_success(self, client):
        project_id = str(uuid4())
        secret_token = "valid-secret"
        bot_token = "client_bot_token"
        update = {"update_id": 12345, "message": {"chat": {"id": 111}, "text": "Hello"}}
        expected_update = update.copy()
        expected_update["_bot_token"] = bot_token

        with patch("src.interfaces.http.webhooks.ProjectTokenRepository") as MockTokens:
            tokens = AsyncMock()
            tokens.get_webhook_secret = AsyncMock(return_value=secret_token)
            tokens.get_bot_token = AsyncMock(return_value=bot_token)
            MockTokens.return_value = tokens

            with patch("src.interfaces.http.webhooks.settings.ADMIN_BOT_TOKEN", "admin_token"):
                with patch("src.interfaces.http.webhooks.process_client_update", new_callable=AsyncMock) as process:
                    process.return_value = {"ok": True}
                    response = client.post(
                        f"/webhook/{project_id}",
                        json=update,
                        headers={"X-Telegram-Bot-Api-Secret-Token": secret_token},
                    )

        assert response.status_code == 200
        assert response.json() == {"ok": True}
        process.assert_awaited_once_with(
            expected_update,
            project_id,
            app.dependency_overrides[get_orchestrator](),
            bot_token,
        )

    def test_legacy_webhook_rejects_platform_bot_token(self, client):
        project_id = str(uuid4())
        secret_token = "valid-secret"
        admin_token = "admin_token"

        with patch("src.interfaces.http.webhooks.ProjectTokenRepository") as MockTokens:
            tokens = AsyncMock()
            tokens.get_bot_token = AsyncMock(return_value=admin_token)
            MockTokens.return_value = tokens

            with patch("src.interfaces.http.webhooks.settings.ADMIN_BOT_TOKEN", admin_token):
                response = client.post(
                    f"/webhook/{project_id}",
                    json={"update_id": 1},
                    headers={"X-Telegram-Bot-Api-Secret-Token": secret_token},
                )

        assert response.status_code == 409
        assert response.json()["detail"] == "Platform bot must use /webhooks/platform"

    def test_webhook_missing_secret_token(self, client):
        response = client.post(f"/webhook/{uuid4()}", json={})
        assert response.status_code == 401
        assert response.json()["detail"] == "Missing secret token"

    def test_webhook_invalid_secret_token(self, client):
        project_id = str(uuid4())

        with patch("src.interfaces.http.webhooks.ProjectTokenRepository") as MockTokens:
            tokens = AsyncMock()
            tokens.get_bot_token = AsyncMock(return_value="some_token")
            tokens.get_webhook_secret = AsyncMock(return_value="valid-secret")
            MockTokens.return_value = tokens

            response = client.post(
                f"/webhook/{project_id}",
                json={"update_id": 1},
                headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"},
            )

        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid secret token"

    def test_webhook_project_not_found(self, client):
        project_id = str(uuid4())

        with patch("src.interfaces.http.webhooks.ProjectTokenRepository") as MockTokens:
            tokens = AsyncMock()
            tokens.get_bot_token = AsyncMock(return_value=None)
            MockTokens.return_value = tokens

            response = client.post(
                f"/webhook/{project_id}",
                json={},
                headers={"X-Telegram-Bot-Api-Secret-Token": "valid-secret"},
            )

        assert response.status_code == 404
        assert response.json()["detail"] == "Project not found"

    def test_manager_webhook_success(self, client):
        secret_token = "manager-secret"
        project_id = str(uuid4())
        manager_chat_id = 12345
        manager_bot_token = "manager_bot_token"
        update = {"message": {"from": {"id": manager_chat_id}, "chat": {"id": manager_chat_id}, "text": "reply"}}
        expected_update = update.copy()
        expected_update["_bot_token"] = manager_bot_token
        expected_update["_manager_user_id"] = "11111111-1111-1111-1111-111111111111"

        with patch("src.interfaces.http.webhooks.ProjectTokenRepository") as MockTokens:
            with patch("src.interfaces.http.webhooks.ProjectMemberRepository") as MockMembers:
                tokens = AsyncMock()
                tokens.find_project_by_manager_webhook_secret = AsyncMock(return_value=project_id)
                tokens.get_manager_bot_token = AsyncMock(return_value=manager_bot_token)
                MockTokens.return_value = tokens

                members = AsyncMock()
                members.get_manager_notification_targets = AsyncMock(return_value=[str(manager_chat_id)])
                members.resolve_manager_user_id_by_telegram = AsyncMock(return_value="11111111-1111-1111-1111-111111111111")
                MockMembers.return_value = members

                with patch("src.interfaces.http.webhooks.process_manager_update", new_callable=AsyncMock) as process:
                    process.return_value = {"ok": True}
                    response = client.post(
                        "/manager/webhook",
                        json=update,
                        headers={"X-Telegram-Bot-Api-Secret-Token": secret_token},
                    )

        assert response.status_code == 200
        assert response.json() == {"ok": True}
        process.assert_awaited_once_with(
            expected_update,
            project_id,
            app.dependency_overrides[get_orchestrator](),
            manager_bot_token,
        )

    def test_manager_webhook_missing_secret_token(self, client):
        response = client.post("/manager/webhook", json={})
        assert response.status_code == 401
        assert response.json()["detail"] == "Missing secret token"

    def test_manager_webhook_invalid_secret_token(self, client):
        with patch("src.interfaces.http.webhooks.ProjectTokenRepository") as MockTokens:
            tokens = AsyncMock()
            tokens.find_project_by_manager_webhook_secret = AsyncMock(return_value=None)
            MockTokens.return_value = tokens

            response = client.post(
                "/manager/webhook",
                json={},
                headers={"X-Telegram-Bot-Api-Secret-Token": "wrong"},
            )

        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid secret token"

    def test_manager_webhook_missing_manager_token(self, client):
        with patch("src.interfaces.http.webhooks.ProjectTokenRepository") as MockTokens:
            with patch("src.interfaces.http.webhooks.ProjectMemberRepository"):
                tokens = AsyncMock()
                tokens.find_project_by_manager_webhook_secret = AsyncMock(return_value=str(uuid4()))
                tokens.get_manager_bot_token = AsyncMock(return_value=None)
                MockTokens.return_value = tokens

                response = client.post(
                    "/manager/webhook",
                    json={},
                    headers={"X-Telegram-Bot-Api-Secret-Token": "manager-secret"},
                )

        assert response.status_code == 500
        assert response.json()["detail"] == "Manager token error"

    def test_manager_webhook_unauthorized_chat_id(self, client):
        project_id = str(uuid4())
        manager_chat_id = 12345

        with patch("src.interfaces.http.webhooks.ProjectTokenRepository") as MockTokens:
            with patch("src.interfaces.http.webhooks.ProjectMemberRepository") as MockMembers:
                tokens = AsyncMock()
                tokens.find_project_by_manager_webhook_secret = AsyncMock(return_value=project_id)
                tokens.get_manager_bot_token = AsyncMock(return_value="manager_bot_token")
                MockTokens.return_value = tokens

                members = AsyncMock()
                members.get_manager_notification_targets = AsyncMock(return_value=["99999"])
                members.resolve_manager_user_id_by_telegram = AsyncMock(return_value=None)
                MockMembers.return_value = members

                with patch("src.interfaces.http.webhooks.process_manager_update", new_callable=AsyncMock) as process:
                    response = client.post(
                        "/manager/webhook",
                        json={"message": {"from": {"id": manager_chat_id}}},
                        headers={"X-Telegram-Bot-Api-Secret-Token": "manager-secret"},
                    )

        assert response.status_code == 200
        assert response.json() == {"ok": True}
        process.assert_not_awaited()

    def test_manager_webhook_no_chat_id(self, client):
        project_id = str(uuid4())

        with patch("src.interfaces.http.webhooks.ProjectTokenRepository") as MockTokens:
            with patch("src.interfaces.http.webhooks.ProjectMemberRepository") as MockMembers:
                tokens = AsyncMock()
                tokens.find_project_by_manager_webhook_secret = AsyncMock(return_value=project_id)
                tokens.get_manager_bot_token = AsyncMock(return_value="token")
                MockTokens.return_value = tokens

                members = AsyncMock()
                members.get_manager_notification_targets = AsyncMock(return_value=["123"])
                MockMembers.return_value = members

                with patch("src.interfaces.http.webhooks.process_manager_update", new_callable=AsyncMock) as process:
                    response = client.post(
                        "/manager/webhook",
                        json={},
                        headers={"X-Telegram-Bot-Api-Secret-Token": "manager-secret"},
                    )

        assert response.status_code == 200
        assert response.json() == {"ok": True}
        process.assert_not_awaited()


def test_legacy_webhook_unexpected_error_uses_safe_500_contract():
    project_id = str(uuid4())
    client = TestClient(app, raise_server_exceptions=False)

    with patch("src.interfaces.http.webhooks.ProjectTokenRepository") as MockTokens:
        tokens = AsyncMock()
        tokens.get_bot_token = AsyncMock(side_effect=RuntimeError("database password leaked"))
        MockTokens.return_value = tokens

        response = client.post(
            f"/webhook/{project_id}",
            json={"update_id": 1},
            headers={
                "X-Telegram-Bot-Api-Secret-Token": "valid-secret",
                "X-Request-ID": "req-webhook-500",
            },
        )

    assert response.status_code == 500
    assert response.headers["X-Request-ID"] == "req-webhook-500"
    assert response.json() == {
        "detail": "Internal server error",
        "request_id": "req-webhook-500",
    }
    assert "database password leaked" not in response.text
