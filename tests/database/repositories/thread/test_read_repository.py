from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.infrastructure.db.repositories.thread.read import ThreadReadRepository


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
def read_repo(mock_pool):
    return ThreadReadRepository(mock_pool)


@pytest.mark.asyncio
async def test_get_dialogs_expands_manager_filter_to_handoff_statuses(
    read_repo, mock_pool
):
    project_id = str(uuid4())
    mock_pool.mock_conn.fetch = AsyncMock(return_value=[])

    await read_repo.get_dialogs(project_id=project_id, status_filter="manager")

    query, stored_project_id, statuses, search, client_id, limit, offset = (
        mock_pool.mock_conn.fetch.await_args.args
    )
    assert "t.status = ANY($2)" in query
    assert str(stored_project_id) == project_id
    assert statuses == ["manual", "waiting_manager"]
    assert search is None
    assert client_id is None
    assert limit == 20
    assert offset == 0


@pytest.mark.asyncio
async def test_get_dialogs_keeps_manual_filter_narrow(read_repo, mock_pool):
    project_id = str(uuid4())
    mock_pool.mock_conn.fetch = AsyncMock(return_value=[])

    await read_repo.get_dialogs(project_id=project_id, status_filter="manual")

    _, _, statuses, _, _, _, _ = mock_pool.mock_conn.fetch.await_args.args
    assert statuses == ["manual"]


@pytest.mark.asyncio
async def test_get_dialogs_keeps_active_filter_narrow(read_repo, mock_pool):
    project_id = str(uuid4())
    mock_pool.mock_conn.fetch = AsyncMock(return_value=[])

    await read_repo.get_dialogs(project_id=project_id, status_filter="active")

    _, _, statuses, _, _, _, _ = mock_pool.mock_conn.fetch.await_args.args
    assert statuses == ["active"]
