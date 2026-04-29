import pytest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from uuid import uuid4

from src.domain.identity.user_views import (
    AuthMethodView,
    AuthMethodsView,
    UserProfileView,
)
from src.interfaces.http.app import app
from src.interfaces.http.dependencies import get_user_repository, get_current_user_id


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


def user_view(user_id=None, **kwargs):
    return UserProfileView(
        id=user_id or str(uuid4()),
        username=kwargs.get("username"),
        email=kwargs.get("email"),
        full_name=kwargs.get("full_name"),
        telegram_id=kwargs.get("telegram_id"),
        is_platform_admin=kwargs.get("is_platform_admin", False),
    )


def methods_view(user_id, methods=None, has_password=False):
    return AuthMethodsView(
        user_id=user_id,
        methods=methods or [],
        has_password=has_password,
    )


class TestAuthAPI:
    def test_telegram_auth_new_user(self, client, mock_user_repo):
        user_id = str(uuid4())
        mock_user_repo.get_or_create_by_telegram = AsyncMock(
            return_value=(user_id, True)
        )

        with patch("src.interfaces.http.auth.verify", return_value=True):
            response = client.post(
                "/api/auth/telegram",
                json={
                    "id": 12345,
                    "first_name": "John",
                    "username": "johndoe",
                    "auth_date": 1234567890,
                    "hash": "dummy",
                },
            )

        assert response.status_code == 200
        assert response.json()["user_id"] == user_id
        mock_user_repo.get_or_create_by_telegram.assert_awaited_once_with(
            12345, "John", "johndoe", None
        )

    def test_telegram_auth_existing_user(self, client, mock_user_repo):
        user_id = str(uuid4())
        mock_user_repo.get_or_create_by_telegram = AsyncMock(
            return_value=(user_id, False)
        )

        with patch("src.interfaces.http.auth.verify", return_value=True):
            response = client.post(
                "/api/auth/telegram",
                json={
                    "id": 12345,
                    "first_name": "John",
                    "username": "johndoe",
                    "auth_date": 1234567890,
                    "hash": "dummy",
                },
            )

        assert response.status_code == 200
        assert response.json()["user_id"] == user_id

    def test_telegram_auth_with_last_name_passes_full_profile(
        self, client, mock_user_repo
    ):
        user_id = str(uuid4())
        mock_user_repo.get_or_create_by_telegram = AsyncMock(
            return_value=(user_id, False)
        )

        with patch("src.interfaces.http.auth.verify", return_value=True):
            response = client.post(
                "/api/auth/telegram",
                json={
                    "id": 12345,
                    "first_name": "John",
                    "last_name": "Doe",
                    "username": "johndoe",
                    "auth_date": 1234567890,
                    "hash": "dummy",
                },
            )

        assert response.status_code == 200
        assert response.json()["full_name"] == "John Doe"
        mock_user_repo.get_or_create_by_telegram.assert_awaited_once_with(
            12345, "John", "johndoe", "Doe"
        )

    def test_telegram_auth_invalid_signature(self, client):
        with patch("src.interfaces.http.auth.verify", return_value=False):
            response = client.post(
                "/api/auth/telegram",
                json={
                    "id": 12345,
                    "first_name": "John",
                    "auth_date": 1234567890,
                    "hash": "dummy",
                },
            )

        assert response.status_code == 401

    def test_telegram_auth_missing_fields(self, client):
        response = client.post(
            "/api/auth/telegram", json={"id": 12345, "first_name": "John"}
        )
        assert response.status_code == 422

    def test_telegram_auth_invalid_types(self, client):
        response = client.post(
            "/api/auth/telegram",
            json={
                "id": "bad",
                "first_name": "John",
                "auth_date": 1234567890,
                "hash": "dummy",
            },
        )
        assert response.status_code == 422

    def test_get_me(self, client, mock_user_repo):
        user_id = str(uuid4())
        mock_user_repo.get_user_by_id_view = AsyncMock(
            return_value=user_view(
                user_id,
                telegram_id=12345,
                username="johndoe",
                full_name="John",
                email="john@example.com",
            )
        )
        app.dependency_overrides[get_current_user_id] = lambda: user_id
        try:
            response = client.get("/api/auth/me")
        finally:
            app.dependency_overrides.pop(get_current_user_id, None)

        assert response.status_code == 200
        assert response.json()["id"] == user_id

    def test_get_auth_methods(self, client, mock_user_repo):
        user_id = str(uuid4())
        mock_user_repo.list_auth_methods_view = AsyncMock(
            return_value=methods_view(
                user_id,
                [
                    AuthMethodView(
                        provider="email", provider_id="user@example.com", verified=True
                    )
                ],
                has_password=True,
            )
        )
        app.dependency_overrides[get_current_user_id] = lambda: user_id
        try:
            response = client.get("/api/auth/methods")
        finally:
            app.dependency_overrides.pop(get_current_user_id, None)

        assert response.status_code == 200
        assert response.json()["user_id"] == user_id

    def test_email_register(self, client, mock_user_repo):
        user_id = str(uuid4())
        mock_user_repo.get_user_by_identity_view = AsyncMock(return_value=None)
        mock_user_repo.get_or_create_by_email = AsyncMock(return_value=(user_id, True))
        mock_user_repo.set_password = AsyncMock()
        mock_user_repo.get_user_by_id_view = AsyncMock(
            return_value=user_view(user_id, full_name="Jane Doe")
        )

        response = client.post(
            "/api/auth/email/register",
            json={
                "email": "Jane@Example.com",
                "password": "super-secret",
                "full_name": "Jane Doe",
            },
        )

        assert response.status_code == 200
        assert response.json()["user_id"] == user_id

    def test_email_register_conflict(self, client, mock_user_repo):
        mock_user_repo.get_user_by_identity_view = AsyncMock(return_value=user_view())

        response = client.post(
            "/api/auth/email/register",
            json={
                "email": "taken@example.com",
                "password": "super-secret",
            },
        )

        assert response.status_code == 409

    def test_email_login_success(self, client, mock_user_repo):
        user_id = str(uuid4())
        mock_user_repo.get_user_by_identity_view = AsyncMock(
            return_value=user_view(
                user_id,
                username="janedoe",
                full_name="Jane Doe",
            )
        )
        mock_user_repo.verify_password = AsyncMock(return_value=True)

        response = client.post(
            "/api/auth/email/login",
            json={
                "email": "Jane@Example.com",
                "password": "super-secret",
            },
        )

        assert response.status_code == 200
        assert response.json()["user_id"] == user_id

    def test_email_login_invalid_credentials(self, client, mock_user_repo):
        mock_user_repo.get_user_by_identity_view = AsyncMock(return_value=None)
        mock_user_repo.get_user_by_email_view = AsyncMock(return_value=None)

        response = client.post(
            "/api/auth/email/login",
            json={
                "email": "missing@example.com",
                "password": "bad-password",
            },
        )

        assert response.status_code == 401

    def test_link_email_success(self, client, mock_user_repo):
        user_id = str(uuid4())
        app.dependency_overrides[get_current_user_id] = lambda: user_id
        mock_user_repo.get_user_by_identity_view = AsyncMock(return_value=None)
        mock_user_repo.link_email_auth = AsyncMock()
        mock_user_repo.list_auth_methods_view = AsyncMock(
            return_value=methods_view(
                user_id,
                [
                    AuthMethodView(provider="telegram", provider_id="12345"),
                    AuthMethodView(provider="email", provider_id="jane@example.com"),
                ],
                has_password=True,
            )
        )

        try:
            response = client.post(
                "/api/auth/link/email",
                json={
                    "email": "Jane@Example.com",
                    "password": "super-secret",
                },
            )
        finally:
            app.dependency_overrides.pop(get_current_user_id, None)

        assert response.status_code == 200

    def test_link_email_conflict(self, client, mock_user_repo):
        user_id = str(uuid4())
        app.dependency_overrides[get_current_user_id] = lambda: user_id
        mock_user_repo.get_user_by_identity_view = AsyncMock(return_value=user_view())

        try:
            response = client.post(
                "/api/auth/link/email",
                json={
                    "email": "taken@example.com",
                    "password": "super-secret",
                },
            )
        finally:
            app.dependency_overrides.pop(get_current_user_id, None)

        assert response.status_code == 409

    def test_google_login_existing_identity(self, client, mock_user_repo):
        user_id = str(uuid4())
        mock_user_repo.get_user_by_identity_view = AsyncMock(
            return_value=user_view(
                user_id,
                username="google-user",
                full_name="Google User",
            )
        )

        response = client.post(
            "/api/auth/google/login",
            json={
                "provider_subject": "google-sub-123",
                "email": "google@example.com",
                "full_name": "Google User",
            },
        )

        assert response.status_code == 200
        assert response.json()["user_id"] == user_id

    def test_google_login_creates_new_user_without_silent_merge(
        self, client, mock_user_repo
    ):
        user_id = str(uuid4())
        mock_user_repo.get_user_by_identity_view = AsyncMock(return_value=None)
        mock_user_repo.get_user_by_email_view = AsyncMock(return_value=None)
        mock_user_repo.create_user = AsyncMock(return_value=user_id)
        mock_user_repo.link_identity = AsyncMock()
        mock_user_repo.get_user_by_id_view = AsyncMock(
            return_value=user_view(user_id, full_name="Google User")
        )

        response = client.post(
            "/api/auth/google/login",
            json={
                "provider_subject": "google-sub-123",
                "email": "Google@Example.com",
                "full_name": "Google User",
            },
        )

        assert response.status_code == 200
        assert response.json()["user_id"] == user_id

    def test_google_login_conflict_on_existing_email(self, client, mock_user_repo):
        mock_user_repo.get_user_by_identity_view = AsyncMock(return_value=None)
        mock_user_repo.get_user_by_email_view = AsyncMock(return_value=user_view())

        response = client.post(
            "/api/auth/google/login",
            json={
                "provider_subject": "google-sub-123",
                "email": "existing@example.com",
            },
        )

        assert response.status_code == 409

    def test_google_login_with_id_token_success(self, client, mock_user_repo):
        user_id = str(uuid4())
        mock_user_repo.get_user_by_identity_view = AsyncMock(return_value=None)
        mock_user_repo.get_user_by_email_view = AsyncMock(return_value=None)
        mock_user_repo.create_user = AsyncMock(return_value=user_id)
        mock_user_repo.link_identity = AsyncMock()
        mock_user_repo.get_user_by_id_view = AsyncMock(
            return_value=user_view(user_id, full_name="Google User")
        )

        google_profile = {
            "provider_subject": "google-sub-123",
            "email": "google@example.com",
            "full_name": "Google User",
        }

        with patch(
            "src.application.services.auth_service.AuthService.verify_google_id_token",
            AsyncMock(return_value=google_profile),
        ):
            response = client.post(
                "/api/auth/google/login/id-token", json={"id_token": "id-token"}
            )

        assert response.status_code == 200
        assert response.json()["user_id"] == user_id

    def test_link_google_success(self, client, mock_user_repo):
        user_id = str(uuid4())
        app.dependency_overrides[get_current_user_id] = lambda: user_id
        mock_user_repo.get_user_by_identity_view = AsyncMock(return_value=None)
        mock_user_repo.get_user_by_email_view = AsyncMock(return_value=None)
        mock_user_repo.get_user_by_id_view = AsyncMock(return_value=user_view(user_id))
        mock_user_repo.link_identity = AsyncMock()
        mock_user_repo.update_user = AsyncMock()
        mock_user_repo.list_auth_methods_view = AsyncMock(
            return_value=methods_view(
                user_id,
                [AuthMethodView(provider="google", provider_id="google-sub-123")],
                has_password=False,
            )
        )

        try:
            response = client.post(
                "/api/auth/link/google",
                json={
                    "provider_subject": "google-sub-123",
                    "email": "google@example.com",
                },
            )
        finally:
            app.dependency_overrides.pop(get_current_user_id, None)

        assert response.status_code == 200

    def test_link_google_conflict(self, client, mock_user_repo):
        user_id = str(uuid4())
        app.dependency_overrides[get_current_user_id] = lambda: user_id
        mock_user_repo.get_user_by_identity_view = AsyncMock(return_value=user_view())

        try:
            response = client.post(
                "/api/auth/link/google",
                json={
                    "provider_subject": "google-sub-123",
                },
            )
        finally:
            app.dependency_overrides.pop(get_current_user_id, None)

        assert response.status_code == 409

    def test_link_google_with_id_token_success(self, client, mock_user_repo):
        user_id = str(uuid4())
        app.dependency_overrides[get_current_user_id] = lambda: user_id
        mock_user_repo.get_user_by_identity_view = AsyncMock(return_value=None)
        mock_user_repo.get_user_by_email_view = AsyncMock(return_value=None)
        mock_user_repo.get_user_by_id_view = AsyncMock(return_value=user_view(user_id))
        mock_user_repo.link_identity = AsyncMock()
        mock_user_repo.update_user = AsyncMock()
        mock_user_repo.list_auth_methods_view = AsyncMock(
            return_value=methods_view(
                user_id,
                [AuthMethodView(provider="google", provider_id="google-sub-123")],
                has_password=False,
            )
        )

        google_profile = {
            "provider_subject": "google-sub-123",
            "email": "google@example.com",
            "full_name": "Google User",
        }

        try:
            with patch(
                "src.application.services.auth_service.AuthService.verify_google_id_token",
                AsyncMock(return_value=google_profile),
            ):
                response = client.post(
                    "/api/auth/link/google/id-token", json={"id_token": "id-token"}
                )
        finally:
            app.dependency_overrides.pop(get_current_user_id, None)

        assert response.status_code == 200

    def test_change_password_requires_email_auth(self, client, mock_user_repo):
        user_id = str(uuid4())
        app.dependency_overrides[get_current_user_id] = lambda: user_id
        mock_user_repo.has_auth_method = AsyncMock(return_value=False)

        try:
            response = client.post(
                "/api/auth/password/change", json={"new_password": "new-secret"}
            )
        finally:
            app.dependency_overrides.pop(get_current_user_id, None)

        assert response.status_code == 400

    def test_change_password_success_with_existing_password(
        self, client, mock_user_repo
    ):
        user_id = str(uuid4())
        app.dependency_overrides[get_current_user_id] = lambda: user_id
        mock_user_repo.has_auth_method = AsyncMock(return_value=True)
        mock_user_repo.has_password = AsyncMock(return_value=True)
        mock_user_repo.verify_password = AsyncMock(return_value=True)
        mock_user_repo.set_password = AsyncMock()
        mock_user_repo.list_auth_methods_view = AsyncMock(
            return_value=methods_view(
                user_id,
                [AuthMethodView(provider="email", provider_id="user@example.com")],
                has_password=True,
            )
        )

        try:
            response = client.post(
                "/api/auth/password/change",
                json={
                    "current_password": "old-secret",
                    "new_password": "new-secret",
                },
            )
        finally:
            app.dependency_overrides.pop(get_current_user_id, None)

        assert response.status_code == 200

    def test_unlink_auth_method_rejects_last_method(self, client, mock_user_repo):
        user_id = str(uuid4())
        app.dependency_overrides[get_current_user_id] = lambda: user_id
        mock_user_repo.has_auth_method = AsyncMock(return_value=True)
        mock_user_repo.count_auth_methods = AsyncMock(return_value=1)

        try:
            response = client.delete("/api/auth/methods/google")
        finally:
            app.dependency_overrides.pop(get_current_user_id, None)

        assert response.status_code == 400

    def test_unlink_email_requires_non_password_path(self, client, mock_user_repo):
        user_id = str(uuid4())
        app.dependency_overrides[get_current_user_id] = lambda: user_id
        mock_user_repo.has_auth_method = AsyncMock(return_value=True)
        mock_user_repo.count_auth_methods = AsyncMock(return_value=2)
        mock_user_repo.has_password = AsyncMock(return_value=True)

        try:
            response = client.delete("/api/auth/methods/email")
        finally:
            app.dependency_overrides.pop(get_current_user_id, None)

        assert response.status_code == 400

    def test_unlink_auth_method_success(self, client, mock_user_repo):
        user_id = str(uuid4())
        app.dependency_overrides[get_current_user_id] = lambda: user_id
        mock_user_repo.has_auth_method = AsyncMock(return_value=True)
        mock_user_repo.count_auth_methods = AsyncMock(return_value=2)
        mock_user_repo.unlink_identity = AsyncMock(return_value=True)
        mock_user_repo.list_auth_methods_view = AsyncMock(
            return_value=methods_view(
                user_id,
                [AuthMethodView(provider="telegram", provider_id="12345")],
                has_password=False,
            )
        )

        try:
            response = client.delete("/api/auth/methods/google")
        finally:
            app.dependency_overrides.pop(get_current_user_id, None)

        assert response.status_code == 200

    def test_request_email_verification_success(self, client, mock_user_repo):
        user_id = str(uuid4())
        app.dependency_overrides[get_current_user_id] = lambda: user_id
        mock_user_repo.get_user_by_id_view = AsyncMock(
            return_value=user_view(user_id, email="user@example.com")
        )
        mock_user_repo.has_auth_method = AsyncMock(return_value=True)
        mock_user_repo.create_email_verification_token = AsyncMock(
            return_value={
                "token": "verify-token",
                "expires_at": "2030-01-01T00:00:00+00:00",
            }
        )

        try:
            response = client.post("/api/auth/email/verification/request")
        finally:
            app.dependency_overrides.pop(get_current_user_id, None)

        assert response.status_code == 200
        assert response.json()["token"] == "verify-token"

    def test_confirm_email_verification_success(self, client, mock_user_repo):
        user_id = str(uuid4())
        mock_user_repo.consume_email_verification_token = AsyncMock(
            return_value={
                "user_id": user_id,
                "email": "user@example.com",
            }
        )
        mock_user_repo.mark_email_verified = AsyncMock()
        mock_user_repo.list_auth_methods_view = AsyncMock(
            return_value=methods_view(
                user_id,
                [
                    AuthMethodView(
                        provider="email", provider_id="user@example.com", verified=True
                    )
                ],
                has_password=True,
            )
        )

        response = client.post(
            "/api/auth/email/verification/confirm", json={"token": "verify-token"}
        )

        assert response.status_code == 200

    def test_request_password_reset_generic_success_for_missing_email(
        self, client, mock_user_repo
    ):
        mock_user_repo.get_user_by_identity_view = AsyncMock(return_value=None)
        mock_user_repo.get_user_by_email_view = AsyncMock(return_value=None)

        response = client.post(
            "/api/auth/password/reset/request", json={"email": "missing@example.com"}
        )

        assert response.status_code == 200

    def test_request_password_reset_success(self, client, mock_user_repo):
        user_id = str(uuid4())
        mock_user_repo.get_user_by_identity_view = AsyncMock(
            return_value=user_view(user_id)
        )
        mock_user_repo.has_auth_method = AsyncMock(return_value=True)
        mock_user_repo.create_password_reset_token = AsyncMock(
            return_value={
                "token": "reset-token",
                "expires_at": "2030-01-01T00:00:00+00:00",
            }
        )

        response = client.post(
            "/api/auth/password/reset/request", json={"email": "user@example.com"}
        )

        assert response.status_code == 200
        assert response.json()["token"] == "reset-token"

    def test_confirm_password_reset_success(self, client, mock_user_repo):
        user_id = str(uuid4())
        mock_user_repo.consume_password_reset_token = AsyncMock(
            return_value={"user_id": user_id}
        )
        mock_user_repo.set_password = AsyncMock()

        response = client.post(
            "/api/auth/password/reset/confirm",
            json={
                "token": "reset-token",
                "new_password": "new-secret",
            },
        )

        assert response.status_code == 200
