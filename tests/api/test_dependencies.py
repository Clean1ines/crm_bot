import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException
from fastapi.testclient import TestClient
import jwt
from uuid import uuid4

from src.interfaces.http.app import app
from src.interfaces.http.dependencies import (
    get_current_user_id,
    require_platform_admin,
    verify_pro_mode_access,
    get_pool,
    get_orchestrator,
    get_project_repo,
    get_thread_runtime_state_repo,
    get_thread_read_repo,
    get_thread_message_repo,
    get_thread_lifecycle_repo,
    get_memory_repository,
    get_tool_registry,
    get_redis,
)
from src.infrastructure.db.repositories.thread.lifecycle import (
    ThreadLifecycleRepository,
)
from src.infrastructure.db.repositories.thread.messages import ThreadMessageRepository
from src.infrastructure.db.repositories.thread.read import ThreadReadRepository
from src.infrastructure.db.repositories.thread.runtime_state import (
    ThreadRuntimeStateRepository,
)


class TestGetCurrentUserId:
    @pytest.mark.asyncio
    async def test_success(self):
        user_id = str(uuid4())
        token = "valid.token"
        payload = {"sub": user_id}
        with patch("src.interfaces.http.dependencies.jwt.decode") as mock_decode:
            mock_decode.return_value = payload
            with patch("src.interfaces.http.dependencies.settings") as mock_settings:
                mock_settings.JWT_SECRET_KEY = "secret"
                result = await get_current_user_id(authorization=f"Bearer {token}")
        assert result == user_id
        mock_decode.assert_called_once_with(token, "secret", algorithms=["HS256"])

    @pytest.mark.asyncio
    async def test_missing_authorization_header(self):
        with pytest.raises(HTTPException) as exc:
            await get_current_user_id(authorization=None)
        assert exc.value.status_code == 401
        assert exc.value.detail == "Authorization header required"

    @pytest.mark.asyncio
    async def test_invalid_token_format(self):
        with pytest.raises(HTTPException) as exc:
            await get_current_user_id(authorization="InvalidToken")
        assert exc.value.status_code == 401
        assert exc.value.detail == "Invalid token format. Use 'Bearer <token>'"

    @pytest.mark.asyncio
    async def test_empty_token(self):
        with patch("src.interfaces.http.dependencies.jwt.decode") as mock_decode:
            mock_decode.side_effect = jwt.InvalidTokenError
            with patch("src.interfaces.http.dependencies.settings") as mock_settings:
                mock_settings.JWT_SECRET_KEY = "secret"
                with pytest.raises(HTTPException) as exc:
                    await get_current_user_id(authorization="Bearer ")
        assert exc.value.status_code == 401
        assert exc.value.detail == "Invalid token"

    @pytest.mark.asyncio
    async def test_expired_token(self):
        with patch("src.interfaces.http.dependencies.jwt.decode") as mock_decode:
            mock_decode.side_effect = jwt.ExpiredSignatureError
            with patch("src.interfaces.http.dependencies.settings") as mock_settings:
                mock_settings.JWT_SECRET_KEY = "secret"
                with pytest.raises(HTTPException) as exc:
                    await get_current_user_id(authorization="Bearer expired")
        assert exc.value.status_code == 401
        assert exc.value.detail == "Token expired"

    @pytest.mark.asyncio
    async def test_invalid_token_signature(self):
        with patch("src.interfaces.http.dependencies.jwt.decode") as mock_decode:
            mock_decode.side_effect = jwt.InvalidTokenError
            with patch("src.interfaces.http.dependencies.settings") as mock_settings:
                mock_settings.JWT_SECRET_KEY = "secret"
                with pytest.raises(HTTPException) as exc:
                    await get_current_user_id(authorization="Bearer invalid")
        assert exc.value.status_code == 401
        assert exc.value.detail == "Invalid token"

    @pytest.mark.asyncio
    async def test_missing_sub_claim(self):
        token = "valid.token"
        payload = {}
        with patch("src.interfaces.http.dependencies.jwt.decode") as mock_decode:
            mock_decode.return_value = payload
            with patch("src.interfaces.http.dependencies.settings") as mock_settings:
                mock_settings.JWT_SECRET_KEY = "secret"
                with pytest.raises(ValueError, match="Missing subject claim"):
                    await get_current_user_id(authorization=f"Bearer {token}")


class TestRequirePlatformAdmin:
    @pytest.mark.asyncio
    async def test_success(self):
        user_repo = AsyncMock()
        user_repo.is_platform_admin = AsyncMock(return_value=True)

        result = await require_platform_admin(
            current_user_id="user-id",
            user_repo=user_repo,
        )

        assert result == "user-id"
        user_repo.is_platform_admin.assert_awaited_once_with("user-id")

    @pytest.mark.asyncio
    async def test_forbidden_for_regular_user(self):
        user_repo = AsyncMock()
        user_repo.is_platform_admin = AsyncMock(return_value=False)

        with pytest.raises(HTTPException) as exc:
            await require_platform_admin(
                current_user_id="user-id",
                user_repo=user_repo,
            )

        assert exc.value.status_code == 403
        assert exc.value.detail == "Platform admin required"


class TestVerifyProModeAccess:
    @pytest.mark.asyncio
    async def test_success(self):
        project_repo = AsyncMock()
        project_repo.get_is_pro_mode = AsyncMock(return_value=True)
        check_pro_mode = verify_pro_mode_access(project_repo=project_repo)
        result = await check_pro_mode("project-id")
        assert result is True
        project_repo.get_is_pro_mode.assert_awaited_once_with("project-id")

    @pytest.mark.asyncio
    async def test_pro_mode_disabled(self):
        project_repo = AsyncMock()
        project_repo.get_is_pro_mode = AsyncMock(return_value=False)
        check_pro_mode = verify_pro_mode_access(project_repo=project_repo)
        with pytest.raises(HTTPException) as exc:
            await check_pro_mode("project-id")
        assert exc.value.status_code == 403
        assert (
            exc.value.detail
            == "Pro mode required. Upgrade your plan to access this feature."
        )

    @pytest.mark.asyncio
    async def test_pro_mode_repository_error_fails_closed(self):
        project_repo = AsyncMock()
        project_repo.get_is_pro_mode = AsyncMock(side_effect=RuntimeError("db down"))
        check_pro_mode = verify_pro_mode_access(project_repo=project_repo)

        with pytest.raises(HTTPException) as exc:
            await check_pro_mode("project-id")

        assert exc.value.status_code == 503
        assert exc.value.detail == "Project runtime guard unavailable"


class TestPoolAndOrchestrator:
    def test_get_pool_success(self):
        with patch(
            "src.interfaces.http.dependencies.src.interfaces.composition.fastapi_lifespan.pool",
            "mock_pool",
        ):
            result = get_pool()
            assert result == "mock_pool"

    def test_get_pool_not_initialized(self):
        with patch(
            "src.interfaces.http.dependencies.src.interfaces.composition.fastapi_lifespan.pool",
            None,
        ):
            with pytest.raises(RuntimeError, match="Database pool not initialized"):
                get_pool()

    def test_get_orchestrator_success(self):
        with patch(
            "src.interfaces.http.dependencies.src.interfaces.composition.fastapi_lifespan.orchestrator",
            "mock_orch",
        ):
            result = get_orchestrator()
            assert result == "mock_orch"

    def test_get_orchestrator_not_initialized(self):
        with patch(
            "src.interfaces.http.dependencies.src.interfaces.composition.fastapi_lifespan.orchestrator",
            None,
        ):
            with pytest.raises(RuntimeError, match="Orchestrator not initialized"):
                get_orchestrator()


class TestRepositoryFactories:
    def test_get_project_repo(self):
        mock_pool = MagicMock()
        with patch(
            "src.interfaces.composition.project_repositories.ProjectRepository"
        ) as MockRepo:
            get_project_repo(pool=mock_pool)
            MockRepo.assert_called_once_with(mock_pool)

    def test_get_thread_lifecycle_repo(self):
        mock_pool = MagicMock()
        repo = get_thread_lifecycle_repo(pool=mock_pool)
        assert isinstance(repo, ThreadLifecycleRepository)
        assert repo.pool is mock_pool

    def test_get_thread_message_repo(self):
        mock_pool = MagicMock()
        repo = get_thread_message_repo(pool=mock_pool)
        assert isinstance(repo, ThreadMessageRepository)
        assert repo.pool is mock_pool

    def test_get_thread_read_repo(self):
        mock_pool = MagicMock()
        repo = get_thread_read_repo(pool=mock_pool)
        assert isinstance(repo, ThreadReadRepository)
        assert repo.pool is mock_pool

    def test_get_thread_runtime_state_repo(self):
        mock_pool = MagicMock()
        repo = get_thread_runtime_state_repo(pool=mock_pool)
        assert isinstance(repo, ThreadRuntimeStateRepository)
        assert repo.pool is mock_pool

    def test_get_memory_repository(self):
        mock_pool = MagicMock()
        with patch("src.interfaces.http.dependencies.MemoryRepository") as MockRepo:
            get_memory_repository(pool=mock_pool)
            MockRepo.assert_called_once_with(mock_pool)


class TestToolRegistry:
    def test_get_tool_registry_success(self):
        mock_registry = MagicMock()
        with patch("src.tools.tool_registry", mock_registry):
            result = get_tool_registry()
            assert result is mock_registry

    def test_get_tool_registry_not_initialized(self):
        with patch("src.tools.tool_registry", None):
            with pytest.raises(RuntimeError, match="ToolRegistry not initialized"):
                get_tool_registry()


class TestGetRedis:
    @pytest.mark.asyncio
    async def test_get_redis(self):
        mock_client = AsyncMock()
        with patch(
            "src.interfaces.http.dependencies.get_redis_client",
            return_value=mock_client,
        ) as mock_get:
            result = await get_redis()
            assert result is mock_client
            mock_get.assert_awaited_once()


class TestGlobalExceptionHandler:
    def test_500_response_does_not_leak_traceback_or_exception_text(self):
        route_path = "/__test_global_exception_handler_safe_500"

        if not any(route.path == route_path for route in app.routes):

            @app.get(route_path)
            async def _raise_unhandled_error():
                raise RuntimeError("secret internal database failure")

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get(route_path, headers={"X-Request-ID": "test-request-id"})

        assert response.status_code == 500
        assert response.headers["X-Request-ID"] == "test-request-id"

        body = response.json()
        assert body == {
            "detail": "Internal server error",
            "request_id": "test-request-id",
        }

        serialized_body = str(body).lower()
        assert "traceback" not in body
        assert "traceback" not in serialized_body
        assert "secret internal database failure" not in serialized_body
        assert "runtimeerror" not in serialized_body
