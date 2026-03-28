import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from uuid import uuid4

from src.main import app
from src.api.dependencies import verify_admin_token


@pytest.fixture(autouse=True)
def mock_lifespan():
    with patch("asyncpg.create_pool") as mock_pool:
        mock_pool.return_value = AsyncMock()
        yield


@pytest.fixture
def client():
    return TestClient(app)


class TestRateLimitsAPI:
    """Тесты для GET /limits"""

    def test_get_rate_limits_success(self, client):
        """Успешное получение лимитов"""
        # Мокируем ModelRegistry и RateLimitTracker
        mock_models = [
            {"id": "model1", "name": "Model One"},
            {"id": "model2", "name": "Model Two"}
        ]
        mock_limits = {
            "model1": {
                "requests_remaining": "100",
                "requests_reset": "1m30s",
                "tokens_remaining": "5000",
                "tokens_reset": "45s",
                "last_update": "1712345678.123"
            },
            "model2": {
                "requests_remaining": "50",
                "requests_reset": "2m",
                "tokens_remaining": "2500",
                "tokens_reset": "60s",
                "last_update": "1712345679.456"
            }
        }

        with patch("src.api.limits.ModelRegistry") as MockRegistry:
            mock_registry = MockRegistry.return_value
            mock_registry.get_all_models.return_value = mock_models

            with patch("src.api.limits.RateLimitTracker") as MockTracker:
                mock_tracker = MockTracker.return_value
                mock_tracker.get_all_remaining = AsyncMock(return_value=mock_limits)

                # Подменяем настройки токена для успешной аутентификации
                with patch("src.core.config.settings.ADMIN_API_TOKEN", "valid-token"):
                    headers = {"Authorization": "Bearer valid-token"}
                    response = client.get("/limits", headers=headers)

        assert response.status_code == 200
        data = response.json()
        assert "models" in data
        assert data["models"] == mock_limits

        # Проверяем вызовы
        mock_registry.get_all_models.assert_called_once()
        mock_tracker.get_all_remaining.assert_awaited_once_with(["model1", "model2"])

    def test_get_rate_limits_no_models(self, client):
        """Пустой список моделей"""
        with patch("src.api.limits.ModelRegistry") as MockRegistry:
            mock_registry = MockRegistry.return_value
            mock_registry.get_all_models.return_value = []

            with patch("src.api.limits.RateLimitTracker") as MockTracker:
                mock_tracker = MockTracker.return_value
                mock_tracker.get_all_remaining = AsyncMock(return_value={})

                with patch("src.core.config.settings.ADMIN_API_TOKEN", "valid-token"):
                    headers = {"Authorization": "Bearer valid-token"}
                    response = client.get("/limits", headers=headers)

        assert response.status_code == 200
        assert response.json() == {"models": {}}

    def test_get_rate_limits_missing_token(self, client):
        """Отсутствует токен"""
        response = client.get("/limits")
        assert response.status_code == 401
        assert response.json()["detail"] == "Authorization header required"

    def test_get_rate_limits_invalid_token_format(self, client):
        """Неверный формат токена (нет 'Bearer ')"""
        headers = {"Authorization": "InvalidToken"}
        response = client.get("/limits", headers=headers)
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid token format. Use 'Bearer <token>'"

    def test_get_rate_limits_wrong_token(self, client):
        """Неверный токен (не совпадает с ADMIN_API_TOKEN)"""
        with patch("src.core.config.settings.ADMIN_API_TOKEN", "correct-token"):
            headers = {"Authorization": "Bearer wrong-token"}
            response = client.get("/limits", headers=headers)
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid admin token"
