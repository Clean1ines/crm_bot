from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.infrastructure.db.repositories.thread.lifecycle import (
    ThreadLifecycleRepository,
)


@pytest.fixture
def mock_pool():
    pool = AsyncMock()
    mock_conn = AsyncMock()
    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_conn
    mock_cm.__aexit__.return_value = None
    pool.acquire = MagicMock(return_value=mock_cm)
    pool.mock_conn = mock_conn
    return pool


@pytest.fixture
def lifecycle_repo(mock_pool):
    return ThreadLifecycleRepository(mock_pool)


@pytest.mark.asyncio
async def test_get_or_create_client_persists_clean_username_and_full_name(
    lifecycle_repo, mock_pool
):
    project_id = str(uuid4())
    client_id = uuid4()
    mock_pool.mock_conn.fetchrow = AsyncMock(return_value={"id": client_id})

    result = await lifecycle_repo.get_or_create_client(
        project_id=project_id,
        chat_id=12345,
        username="  alice  ",
        full_name="  Alice Smith  ",
    )

    sql, stored_project_id, chat_id, username, source, full_name = (
        mock_pool.mock_conn.fetchrow.await_args.args
    )
    assert (
        "INSERT INTO clients (project_id, chat_id, username, source, user_id, full_name)"
        in sql
    )
    assert "username = COALESCE(NULLIF(EXCLUDED.username, ''), clients.username)" in sql
    assert (
        "full_name = COALESCE(NULLIF(EXCLUDED.full_name, ''), clients.full_name)" in sql
    )
    assert str(stored_project_id) == project_id
    assert chat_id == 12345
    assert username == "alice"
    assert source == "telegram"
    assert full_name == "Alice Smith"
    assert result == str(client_id)


@pytest.mark.asyncio
async def test_get_or_create_client_does_not_write_blank_name_values(
    lifecycle_repo, mock_pool
):
    project_id = str(uuid4())
    client_id = uuid4()
    mock_pool.mock_conn.fetchrow = AsyncMock(return_value={"id": client_id})

    await lifecycle_repo.get_or_create_client(
        project_id=project_id,
        chat_id=12345,
        username="  ",
        full_name="",
    )

    _, _, _, username, _, full_name = mock_pool.mock_conn.fetchrow.await_args.args
    assert username is None
    assert full_name is None
