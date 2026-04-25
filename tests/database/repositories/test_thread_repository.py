import pytest
from unittest.mock import AsyncMock, MagicMock, call, ANY
from uuid import UUID, uuid4
from datetime import datetime
import asyncpg

from src.domain.project_plane.manager_assignments import ManagerActor
from src.infrastructure.db.repositories.thread_repository import ThreadRepository
from src.domain.project_plane.thread_status import ThreadStatus


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
def thread_repo(mock_pool):
    return ThreadRepository(mock_pool)


class TestThreadRepository:
    def test_init(self, thread_repo, mock_pool):
        assert thread_repo.pool is mock_pool

    # ------------------------------------------------------------------
    # get_or_create_client
    # ------------------------------------------------------------------
    @pytest.mark.asyncio

    async def test_find_by_status_success(self, thread_repo, mock_pool):
        status = "active"
        rows = [
            {"id": uuid4(), "client_id": uuid4(), "status": "active", "client_name": "John"},
            {"id": uuid4(), "client_id": uuid4(), "status": "active", "client_name": "Jane"}
        ]
        mock_pool.mock_conn.fetch = AsyncMock(return_value=rows)

        result = await thread_repo.find_by_status(status)

        expected_sql = """
                SELECT t.*, c.full_name as client_name
                FROM threads t
                JOIN clients c ON t.client_id = c.id
                WHERE t.status = $1
                ORDER BY t.updated_at DESC
            """
        mock_pool.mock_conn.fetch.assert_awaited_once_with(expected_sql, status)
        assert len(result) == len(rows)

    @pytest.mark.asyncio
    async def test_find_by_status_empty(self, thread_repo, mock_pool):
        mock_pool.mock_conn.fetch = AsyncMock(return_value=[])
        result = await thread_repo.find_by_status("active")
        assert result == []

    # ------------------------------------------------------------------
    # Connection errors
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_connection_error(self, thread_repo, mock_pool):
        mock_pool.acquire.side_effect = asyncpg.exceptions.ConnectionDoesNotExistError("conn closed")
        with pytest.raises(asyncpg.exceptions.ConnectionDoesNotExistError):
            await thread_repo.get_active_thread(str(uuid4()))

    @pytest.mark.asyncio
    async def test_undefined_table_error(self, thread_repo, mock_pool):
        mock_pool.mock_conn.fetch = AsyncMock(side_effect=asyncpg.exceptions.UndefinedTableError("no table"))
        with pytest.raises(asyncpg.exceptions.UndefinedTableError):
            await thread_repo.get_messages_for_langgraph(str(uuid4()))
