import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from uuid import uuid4

from src.main import app
from src.api.dependencies import get_user_repository


@pytest.fixture
def mock_user_repo():
    return AsyncMock()


@pytest.fixture(autouse=True)
def override_dependencies(mock_user_repo):
    original_get_user_repo = app.dependency_overrides.get(get_user_repository)

    app.dependency_overrides[get_user_repository] = lambda: mock_user_repo

    yield

    if original_get_user_repo is not None:
        app.dependency_overrides[get_user_repository] = original_get_user_repo
    else:
        app.dependency_overrides.pop(get_user_repository, None)


@pytest.fixture(autouse=True)
def mock_lifespan():
    with patch("asyncpg.create_pool") as mock_pool:
        mock_pool.return_value = AsyncMock()
        yield


@pytest.fixture
def client():
    return TestClient(app)


class TestAuthAPI:

    def test_telegram_auth_new_user(self, client, mock_user_repo):
        user_id = str(uuid4())
        mock_user_repo.get_or_create_by_telegram = AsyncMock(return_value=(user_id, True))

        with patch("src.api.auth.verify") as mock_verify:
            mock_verify.return_value = True
            request_data = {
                "id": 12345,
                "first_name": "John",
                "username": "johndoe",
                "auth_date": 1234567890,
                "hash": "dummy"
            }
            response = client.post("/api/auth/telegram", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == user_id
        assert "access_token" in data
        mock_user_repo.get_or_create_by_telegram.assert_awaited_once_with(12345, "John", "johndoe")

    def test_telegram_auth_existing_user(self, client, mock_user_repo):
        user_id = str(uuid4())
        mock_user_repo.get_or_create_by_telegram = AsyncMock(return_value=(user_id, False))

        with patch("src.api.auth.verify") as mock_verify:
            mock_verify.return_value = True
            request_data = {
                "id": 12345,
                "first_name": "John",
                "username": "johndoe",
                "auth_date": 1234567890,
                "hash": "dummy"
            }
            response = client.post("/api/auth/telegram", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == user_id
        mock_user_repo.get_or_create_by_telegram.assert_awaited_once_with(12345, "John", "johndoe")

    def test_telegram_auth_invalid_signature(self, client):
        with patch("src.api.auth.verify") as mock_verify:
            mock_verify.return_value = False
            request_data = {
                "id": 12345,
                "first_name": "John",
                "username": "johndoe",
                "auth_date": 1234567890,
                "hash": "dummy"
            }
            response = client.post("/api/auth/telegram", json=request_data)

        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid Telegram signature"

    def test_telegram_auth_missing_bot_token(self, client):
        from src.core.config import settings

        with patch.object(settings, "ADMIN_BOT_TOKEN", ""):
            with patch("src.api.auth.verify") as mock_verify:
                mock_verify.return_value = False  # verify вернёт False из-за пустого токена
                request_data = {
                    "id": 12345,
                    "first_name": "John",
                    "username": "johndoe",
                    "auth_date": 1234567890,
                    "hash": "dummy"
                }
                response = client.post("/api/auth/telegram", json=request_data)

        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid Telegram signature"

    def test_telegram_auth_missing_fields(self, client):
        request_data = {
            "id": 12345,
            "first_name": "John",
            # missing auth_date and hash
        }
        response = client.post("/api/auth/telegram", json=request_data)
        assert response.status_code == 422
        errors = response.json()["detail"]
        # Проверяем, что есть ошибки по auth_date и hash
        locs = [err["loc"] for err in errors]
        assert ["body", "auth_date"] in locs
        assert ["body", "hash"] in locs

    def test_telegram_auth_invalid_types(self, client):
        request_data = {
            "id": "not_a_number",
            "first_name": "John",
            "auth_date": 1234567890,
            "hash": "dummy"
        }
        response = client.post("/api/auth/telegram", json=request_data)
        assert response.status_code == 422
        errors = response.json()["detail"]
        assert any(err["loc"] == ["body", "id"] for err in errors)

    def test_telegram_auth_database_error(self, client, mock_user_repo):
        mock_user_repo.get_or_create_by_telegram.side_effect = Exception("Database connection failed")

        with patch("src.api.auth.verify") as mock_verify:
            mock_verify.return_value = True
            with patch("src.main.logger") as mock_logger:
                request_data = {
                    "id": 12345,
                    "first_name": "John",
                    "username": "johndoe",
                    "auth_date": 1234567890,
                    "hash": "dummy"
                }
                # Клиент выбросит исключение, так как глобальный обработчик может его поймать
                # Но для надёжности просто вызываем и игнорируем, если оно вылетит
                try:
                    client.post("/api/auth/telegram", json=request_data)
                except Exception:
                    pass
                mock_logger.error.assert_called()
                args, _ = mock_logger.error.call_args
                assert "Database connection failed" in str(args)

    def test_telegram_auth_jwt_error(self, client, mock_user_repo):
        user_id = str(uuid4())
        mock_user_repo.get_or_create_by_telegram = AsyncMock(return_value=(user_id, True))

        with patch("src.api.auth.verify") as mock_verify:
            mock_verify.return_value = True
            with patch("src.api.auth.jwt.encode") as mock_jwt:
                mock_jwt.side_effect = Exception("JWT signing error")
                with patch("src.main.logger") as mock_logger:
                    request_data = {
                        "id": 12345,
                        "first_name": "John",
                        "username": "johndoe",
                        "auth_date": 1234567890,
                        "hash": "dummy"
                    }
                    try:
                        client.post("/api/auth/telegram", json=request_data)
                    except Exception:
                        pass
                    mock_logger.error.assert_called()
                    args, _ = mock_logger.error.call_args
                    assert "JWT signing error" in str(args)

    def test_telegram_auth_extra_fields_allowed(self, client, mock_user_repo):
        user_id = str(uuid4())
        mock_user_repo.get_or_create_by_telegram = AsyncMock(return_value=(user_id, True))

        with patch("src.api.auth.verify") as mock_verify:
            mock_verify.return_value = True
            request_data = {
                "id": 12345,
                "first_name": "John",
                "username": "johndoe",
                "auth_date": 1234567890,
                "hash": "dummy",
                "last_name": "Doe",      # extra field
                "photo_url": "http://example.com/photo.jpg"
            }
            response = client.post("/api/auth/telegram", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert data["user_id"] == user_id
        mock_user_repo.get_or_create_by_telegram.assert_awaited_once_with(12345, "John", "johndoe")
