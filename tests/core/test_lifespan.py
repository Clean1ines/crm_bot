from unittest.mock import AsyncMock, patch

import pytest

from src.infrastructure.app import lifespan


class _AcquireContext:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Pool:
    def __init__(self, conn):
        self.conn = conn
        self.acquire_called = False

    def acquire(self):
        self.acquire_called = True
        return _AcquireContext(self.conn)


@pytest.mark.asyncio
async def test_bootstrap_platform_owner_uses_configured_owner_id():
    conn = AsyncMock()
    conn.fetchval.return_value = "user-1"
    pool = _Pool(conn)

    with (
        patch.object(lifespan.settings, "BOOTSTRAP_PLATFORM_OWNER", True),
        patch.object(lifespan.settings, "PLATFORM_OWNER_TELEGRAM_ID", "777001"),
        patch.object(lifespan.settings, "ADMIN_CHAT_ID", "111001"),
    ):
        user_id = await lifespan.bootstrap_platform_owner(pool)

    assert user_id == "user-1"
    assert pool.acquire_called is True
    conn.fetchval.assert_awaited_once()
    conn.execute.assert_awaited_once()

    insert_user_args = conn.fetchval.await_args.args
    assert "INSERT INTO users" in insert_user_args[0]
    assert "is_platform_admin" in insert_user_args[0]
    assert insert_user_args[1] == 777001
    assert insert_user_args[2] == "Platform Owner"

    insert_identity_args = conn.execute.await_args.args
    assert "INSERT INTO auth_identities" in insert_identity_args[0]
    assert insert_identity_args[1] == "user-1"
    assert insert_identity_args[2] == "777001"


@pytest.mark.asyncio
async def test_bootstrap_platform_owner_falls_back_to_admin_chat_id():
    conn = AsyncMock()
    conn.fetchval.return_value = "user-2"
    pool = _Pool(conn)

    with (
        patch.object(lifespan.settings, "BOOTSTRAP_PLATFORM_OWNER", True),
        patch.object(lifespan.settings, "PLATFORM_OWNER_TELEGRAM_ID", None),
        patch.object(lifespan.settings, "ADMIN_CHAT_ID", "111001"),
    ):
        user_id = await lifespan.bootstrap_platform_owner(pool)

    assert user_id == "user-2"
    assert conn.fetchval.await_args.args[1] == 111001
    assert conn.execute.await_args.args[2] == "111001"


@pytest.mark.asyncio
async def test_bootstrap_platform_owner_can_be_disabled():
    conn = AsyncMock()
    pool = _Pool(conn)

    with patch.object(lifespan.settings, "BOOTSTRAP_PLATFORM_OWNER", False):
        user_id = await lifespan.bootstrap_platform_owner(pool)

    assert user_id is None
    assert pool.acquire_called is False
    conn.fetchval.assert_not_called()
    conn.execute.assert_not_called()
