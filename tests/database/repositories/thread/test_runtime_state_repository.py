from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.infrastructure.db.repositories.thread.runtime_state import (
    ThreadRuntimeStateRepository,
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


@pytest.mark.asyncio
async def test_compare_and_update_ticket_resolution_uses_version_predicate(mock_pool):
    repo = ThreadRuntimeStateRepository(mock_pool)
    thread_id = str(uuid4())
    mock_pool.mock_conn.fetchrow = AsyncMock(return_value={"id": thread_id})

    updated = await repo.compare_and_update_ticket_resolution(
        thread_id,
        expected_version=4,
        summary="summary",
        resolution={"summary_text": "summary", "status": "edited", "version": 5},
    )

    sql, summary, _resolution_json, stored_thread_id, expected_version = (
        mock_pool.mock_conn.fetchrow.await_args.args
    )
    assert updated is True
    assert summary == "summary"
    assert str(stored_thread_id) == thread_id
    assert expected_version == 4
    assert "ticket_resolution,version" in sql
    assert "= $4" in sql
    assert "RETURNING id" in sql


@pytest.mark.asyncio
async def test_compare_and_update_ticket_resolution_returns_false_without_row(
    mock_pool,
):
    repo = ThreadRuntimeStateRepository(mock_pool)
    mock_pool.mock_conn.fetchrow = AsyncMock(return_value=None)

    updated = await repo.compare_and_update_ticket_resolution(
        str(uuid4()),
        expected_version=1,
        summary="summary",
        resolution={"summary_text": "summary", "status": "edited", "version": 2},
    )

    assert updated is False
