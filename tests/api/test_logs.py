import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from uuid import uuid4

from src.main import app


@pytest.fixture(autouse=True)
def mock_lifespan():
    with patch("asyncpg.create_pool") as mock_pool:
        mock_pool.return_value = MagicMock()
        yield


@pytest.fixture
def client():
    return TestClient(app)


class TestFrontendLogs:
    """Тесты для POST /api/logs/frontend"""

    def test_frontend_logs_minimal(self, client):
        """Пустой JSON — дефолтные level='info', message=''"""
        with patch("src.api.logs.logger") as mock_logger:
            response = client.post("/api/logs/frontend", json={})

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        mock_logger.info.assert_called_once_with("", extra={})

    def test_frontend_logs_with_level_and_message(self, client):
        """Переданы level='error' и message"""
        payload = {"level": "error", "message": "Test error message"}
        with patch("src.api.logs.logger") as mock_logger:
            response = client.post("/api/logs/frontend", json=payload)

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        mock_logger.error.assert_called_once_with("Test error message", extra={})

    def test_frontend_logs_with_extra_fields(self, client):
        """Дополнительные поля попадают в extra (кроме level, message, timestamp)"""
        payload = {
            "level": "warn",
            "message": "Warning message",
            "timestamp": "2025-01-01T00:00:00Z",
            "user_id": "123",
            "context": {"page": "dashboard"}
        }
        with patch("src.api.logs.logger") as mock_logger:
            response = client.post("/api/logs/frontend", json=payload)

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

        # Проверяем, что logger.warning вызван с правильным message и extra
        mock_logger.warning.assert_called_once()
        call_args = mock_logger.warning.call_args
        assert call_args[0][0] == "Warning message"
        extra = call_args[1].get("extra", {})
        # timestamp должен быть исключён
        assert extra == {
            "user_id": "123",
            "context": {"page": "dashboard"}
        }

    def test_frontend_logs_unknown_level_fallback_to_info(self, client):
        """Неизвестный уровень — fallback на info"""
        payload = {"level": "critical", "message": "Unknown level message"}
        with patch("src.api.logs.logger") as mock_logger:
            response = client.post("/api/logs/frontend", json=payload)

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        mock_logger.info.assert_called_once_with("Unknown level message", extra={})

    def test_frontend_logs_debug_level(self, client):
        """Уровень debug"""
        payload = {"level": "debug", "message": "Debug message"}
        with patch("src.api.logs.logger") as mock_logger:
            response = client.post("/api/logs/frontend", json=payload)

        assert response.status_code == 200
        mock_logger.debug.assert_called_once_with("Debug message", extra={})

    def test_frontend_logs_missing_message(self, client):
        """Отсутствует поле message — дефолт ''"""
        payload = {"level": "info"}
        with patch("src.api.logs.logger") as mock_logger:
            response = client.post("/api/logs/frontend", json=payload)

        assert response.status_code == 200
        mock_logger.info.assert_called_once_with("", extra={})

    def test_frontend_logs_wrong_method(self, client):
        """GET вместо POST → 405"""
        response = client.get("/api/logs/frontend")
        assert response.status_code == 405
        assert response.json()["detail"] == "Method Not Allowed"