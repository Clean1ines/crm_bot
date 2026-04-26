import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from uuid import uuid4

from src.interfaces.http.app import app
from src.interfaces.http.dependencies import require_platform_admin


@pytest.fixture
def client():
    return TestClient(app)


class TestMetricsAggregate:
    """Тесты для POST /api/admin/metrics/aggregate"""

    def _override_auth(self):
        """Временно разрешаем platform-admin доступ."""
        async def dummy_auth():
            return "platform-admin"
        self._original_auth = app.dependency_overrides.get(require_platform_admin)
        app.dependency_overrides[require_platform_admin] = dummy_auth

    def _restore_auth(self):
        """Восстанавливаем оригинальную зависимость."""
        if self._original_auth is not None:
            app.dependency_overrides[require_platform_admin] = self._original_auth
        else:
            app.dependency_overrides.pop(require_platform_admin, None)

    # -------- Успешные сценарии (с моками) ----------
    def test_aggregate_metrics_success(self, client):
        self._override_auth()
        try:
            # Подменяем глобальный пул в lifespan
            with patch("src.interfaces.composition.fastapi_lifespan.pool", MagicMock()):
                # Мокаем QueueRepository по полному пути
                with patch("src.infrastructure.db.repositories.queue_repository.QueueRepository") as MockQueueRepo:
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
            with patch("src.interfaces.composition.fastapi_lifespan.pool", MagicMock()):
                with patch("src.infrastructure.db.repositories.queue_repository.QueueRepository") as MockQueueRepo:
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
            with patch("src.interfaces.composition.fastapi_lifespan.pool", MagicMock()):
                payload = {"date": "2025/01/15"}
                response = client.post("/api/admin/metrics/aggregate", json=payload)
            assert response.status_code == 400
            assert response.json()["detail"] == "Invalid date format. Use YYYY-MM-DD."
        finally:
            self._restore_auth()

    def test_aggregate_metrics_missing_date_field(self, client):
        self._override_auth()
        try:
            with patch("src.interfaces.composition.fastapi_lifespan.pool", MagicMock()):
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
        payload = {"date": "2025-01-15"}
        headers = {"Authorization": "Bearer wrong-token"}
        response = client.post("/api/admin/metrics/aggregate", json=payload, headers=headers)
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid token"
