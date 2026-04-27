import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
import httpx

from src.interfaces.http.app import app


@pytest.fixture(autouse=True)
def mock_lifespan():
    with patch("asyncpg.create_pool") as mock_pool:
        mock_pool.return_value = AsyncMock()
        yield


@pytest.fixture
def client():
    return TestClient(app)


class TestBotAPI:
    def test_get_bot_username_success(self, client):
        """Успешное получение username бота."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "ok": True,
            "result": {"username": "test_bot", "id": 123456789},
        }

        with patch("src.interfaces.http.bot.settings") as mock_settings:
            mock_settings.ADMIN_BOT_TOKEN = "test_token"
            with patch("httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client.__aenter__.return_value.get = AsyncMock(
                    return_value=mock_response
                )
                mock_client_class.return_value = mock_client

                response = client.get("/api/bot/username")

        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "test_bot"
        assert data["id"] == 123456789

    def test_get_bot_username_missing_token(self, client):
        """Отсутствует токен бота."""
        with patch("src.interfaces.http.bot.settings") as mock_settings:
            mock_settings.ADMIN_BOT_TOKEN = ""
            with patch("src.interfaces.http.bot.logger") as mock_logger:
                response = client.get("/api/bot/username")

        assert response.status_code == 500
        # Проверяем, что логгер был вызван с ошибкой NO_BOT_TOKEN
        mock_logger.error.assert_called_with("NO_BOT_TOKEN")

    def test_get_bot_username_invalid_token(self, client):
        """Telegram вернул ok=false."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": False, "description": "Not Found"}

        with patch("src.interfaces.http.bot.settings") as mock_settings:
            mock_settings.ADMIN_BOT_TOKEN = "invalid_token"
            with patch("httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client.__aenter__.return_value.get = AsyncMock(
                    return_value=mock_response
                )
                mock_client_class.return_value = mock_client
                with patch("src.interfaces.http.bot.logger") as mock_logger:
                    response = client.get("/api/bot/username")

        assert response.status_code == 500
        mock_logger.error.assert_called_with("TELEGRAM_ERROR")

    def test_get_bot_username_network_error(self, client):
        """Сетевая ошибка при запросе к Telegram."""
        with patch("src.interfaces.http.bot.settings") as mock_settings:
            mock_settings.ADMIN_BOT_TOKEN = "test_token"
            with patch("httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client.__aenter__.return_value.get = AsyncMock(
                    side_effect=httpx.RequestError(
                        "Connection failed", request=MagicMock()
                    )
                )
                mock_client_class.return_value = mock_client
                with patch("src.interfaces.http.app.logger") as mock_global_logger:
                    # Вызываем эндпоинт, ожидаем, что исключение не будет перехвачено
                    try:
                        client.get("/api/bot/username")
                    except Exception:
                        pass
                    # Проверяем, что глобальный логгер получил ошибку
                    mock_global_logger.error.assert_called()
                    args, _ = mock_global_logger.error.call_args
                    assert "Connection failed" in str(args)

    def test_get_bot_username_invalid_json(self, client):
        """Telegram вернул некорректный JSON."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.side_effect = ValueError("Invalid JSON")

        with patch("src.interfaces.http.bot.settings") as mock_settings:
            mock_settings.ADMIN_BOT_TOKEN = "test_token"
            with patch("httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client.__aenter__.return_value.get = AsyncMock(
                    return_value=mock_response
                )
                mock_client_class.return_value = mock_client
                with patch("src.interfaces.http.app.logger") as mock_global_logger:
                    try:
                        client.get("/api/bot/username")
                    except Exception:
                        pass
                    mock_global_logger.error.assert_called()
                    args, _ = mock_global_logger.error.call_args
                    assert "Invalid JSON" in str(args)

    def test_get_bot_username_missing_result_field(self, client):
        """Ответ Telegram не содержит поля result."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "ok": True
            # нет поля result
        }

        with patch("src.interfaces.http.bot.settings") as mock_settings:
            mock_settings.ADMIN_BOT_TOKEN = "test_token"
            with patch("httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client.__aenter__.return_value.get = AsyncMock(
                    return_value=mock_response
                )
                mock_client_class.return_value = mock_client
                with patch("src.interfaces.http.app.logger") as mock_global_logger:
                    try:
                        client.get("/api/bot/username")
                    except Exception:
                        pass
                    mock_global_logger.error.assert_called()
                    args, _ = mock_global_logger.error.call_args
                    assert "result" in str(args)
