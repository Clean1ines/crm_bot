import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from uuid import uuid4

from src.main import app
from src.api.dependencies import verify_admin_token


@pytest.fixture
def client():
    return TestClient(app)


class TestMetricsAggregate:
    """Тесты для POST /api/admin/metrics/aggregate"""

    def _override_auth(self):
        """Временно отключаем проверку админ-токена."""
        async def dummy_auth():
            pass
        self._original_auth = app.dependency_overrides.get(verify_admin_token)
        app.dependency_overrides[verify_admin_token] = dummy_auth

    def _restore_auth(self):
        """Восстанавливаем оригинальную зависимость."""
        if self._original_auth is not None:
            app.dependency_overrides[verify_admin_token] = self._original_auth
        else:
            app.dependency_overrides.pop(verify_admin_token, None)

    # -------- Успешные сценарии (с моками) ----------
    def test_aggregate_metrics_success(self, client):
        self._override_auth()
        try:
            # Подменяем глобальный пул в lifespan
            with patch("src.core.lifespan.pool", MagicMock()):
                # Мокаем QueueRepository по полному пути
                with patch("src.database.repositories.queue_repository.QueueRepository") as MockQueueRepo:
                    mock_queue = AsyncMock()
                    MockQueueRepo.return_value = mock_queue
                    mock_queue.enqueue = AsyncMock(return_value=str(uuid4()))

                    payload = {"date": "2025-01-15"}
                    response = client.post("/api/admin/metrics/aggregate", json=payload)

            assert response.status_code == 202
            data = response.json()
            assert data["status"] == "accepted"
            assert data["message"] == "Aggregation for 2025-01-15 enqueued."

            mock_queue.enqueue.assert_awaited_once_with(
                task_type="aggregate_metrics",
                payload={"date": "2025-01-15"}
            )
        finally:
            self._restore_auth()

    def test_aggregate_metrics_extra_fields_ignored(self, client):
        self._override_auth()
        try:
            with patch("src.core.lifespan.pool", MagicMock()):
                with patch("src.database.repositories.queue_repository.QueueRepository") as MockQueueRepo:
                    mock_queue = AsyncMock()
                    MockQueueRepo.return_value = mock_queue
                    mock_queue.enqueue = AsyncMock(return_value=str(uuid4()))

                    payload = {"date": "2025-01-15", "extra": "ignored", "another": "field"}
                    response = client.post("/api/admin/metrics/aggregate", json=payload)

            assert response.status_code == 202
            mock_queue.enqueue.assert_awaited_once_with(
                task_type="aggregate_metrics",
                payload={"date": "2025-01-15"}
            )
        finally:
            self._restore_auth()

    # -------- Ошибки валидации (здесь тоже нужен мок pool, чтобы код дошёл до проверки) ----------
    def test_aggregate_metrics_invalid_date_format(self, client):
        self._override_auth()
        try:
            with patch("src.core.lifespan.pool", MagicMock()):
                payload = {"date": "2025/01/15"}
                response = client.post("/api/admin/metrics/aggregate", json=payload)
            assert response.status_code == 400
            assert response.json()["detail"] == "Invalid date format. Use YYYY-MM-DD."
        finally:
            self._restore_auth()

    def test_aggregate_metrics_missing_date_field(self, client):
        self._override_auth()
        try:
            with patch("src.core.lifespan.pool", MagicMock()):
                payload = {}
                response = client.post("/api/admin/metrics/aggregate", json=payload)
            assert response.status_code == 422
            errors = response.json()["detail"]
            assert any(err["loc"] == ["body", "date"] for err in errors)
        finally:
            self._restore_auth()

    # -------- Ошибки аутентификации (без переопределения auth) ----------
    def test_aggregate_metrics_missing_token(self, client):
        payload = {"date": "2025-01-15"}
        response = client.post("/api/admin/metrics/aggregate", json=payload)
        assert response.status_code == 401
        assert response.json()["detail"] == "Authorization header required"

    def test_aggregate_metrics_invalid_token_format(self, client):
        payload = {"date": "2025-01-15"}
        headers = {"Authorization": "InvalidToken"}
        response = client.post("/api/admin/metrics/aggregate", json=payload, headers=headers)
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid token format. Use 'Bearer <token>'"

    def test_aggregate_metrics_wrong_token(self, client):
        with patch("src.core.config.settings.ADMIN_API_TOKEN", "correct-token"):
            payload = {"date": "2025-01-15"}
            headers = {"Authorization": "Bearer wrong-token"}
            response = client.post("/api/admin/metrics/aggregate", json=payload, headers=headers)
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid admin token"