import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4
from datetime import datetime
import asyncpg

from src.infrastructure.db.repositories.event_repository import EventRepository


@pytest.fixture
def mock_pool():
    pool = AsyncMock()
    mock_conn = AsyncMock()
    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_conn
    mock_cm.__aexit__.return_value = None
    # acquire должен быть обычным моком (не AsyncMock), т.к. в asyncpg это не корутина
    pool.acquire = MagicMock(return_value=mock_cm)
    pool.mock_conn = mock_conn
    return pool


@pytest.fixture
def event_repo(mock_pool):
    return EventRepository(mock_pool)


class TestEventRepository:
    def test_init(self, event_repo, mock_pool):
        assert event_repo.pool is mock_pool

    @pytest.mark.asyncio
    async def test_append_success(self, event_repo, mock_pool):
        stream_id = uuid4()
        project_id = uuid4()
        event_type = "message_received"
        payload = {"text": "Hello"}
        expected_id = 123
        mock_pool.fetchrow = AsyncMock(return_value={"id": expected_id})

        result = await event_repo.append(stream_id, project_id, event_type, payload)

        expected_sql = """
            INSERT INTO events (stream_id, project_id, event_type, payload)
            VALUES ($1, $2, $3, $4)
            RETURNING id
            """
        mock_pool.fetchrow.assert_awaited_once_with(
            expected_sql, stream_id, project_id, event_type, '{"text": "Hello"}'
        )
        assert result == expected_id

    @pytest.mark.asyncio
    async def test_append_foreign_key_error(self, event_repo, mock_pool):
        stream_id = uuid4()
        project_id = uuid4()
        event_type = "message_received"
        payload = {"text": "Hello"}
        mock_pool.fetchrow = AsyncMock(side_effect=asyncpg.exceptions.ForeignKeyViolationError("fk"))

        with pytest.raises(asyncpg.exceptions.ForeignKeyViolationError):
            await event_repo.append(stream_id, project_id, event_type, payload)

    @pytest.mark.asyncio
    async def test_append_not_null_error(self, event_repo, mock_pool):
        stream_id = uuid4()
        project_id = uuid4()
        event_type = "message_received"
        payload = {"text": "Hello"}
        mock_pool.fetchrow = AsyncMock(side_effect=asyncpg.exceptions.NotNullViolationError("not null"))

        with pytest.raises(asyncpg.exceptions.NotNullViolationError):
            await event_repo.append(stream_id, project_id, event_type, payload)

    @pytest.mark.asyncio
    async def test_append_type_error(self, event_repo, mock_pool):
        stream_id = uuid4()
        project_id = uuid4()
        event_type = "message_received"
        payload = {"date": datetime.now()}
        with pytest.raises(TypeError):
            await event_repo.append(stream_id, project_id, event_type, payload)

    @pytest.mark.asyncio
    async def test_get_stream_without_after_id_success(self, event_repo, mock_pool):
        stream_id = uuid4()
        limit = 100
        expected_rows = [
            {"id": 1, "event_type": "type1", "payload": {"a": 1}, "created_at": "2021-01-01"},
            {"id": 2, "event_type": "type2", "payload": {"b": 2}, "created_at": "2021-01-02"},
        ]
        mock_pool.fetch = AsyncMock(return_value=expected_rows)

        events = await event_repo.get_stream(stream_id, limit)

        expected_sql = """
                SELECT id, event_type, payload, created_at
                FROM events
                WHERE stream_id = $1
                ORDER BY created_at ASC
                LIMIT $2
                """
        mock_pool.fetch.assert_awaited_once_with(expected_sql, stream_id, limit)
        assert len(events) == 2
        assert events[0]["id"] == 1
        assert events[0]["type"] == "type1"
        assert events[0]["payload"] == {"a": 1}
        assert events[0]["ts"] == "2021-01-01"

    @pytest.mark.asyncio
    async def test_get_stream_with_after_id_success(self, event_repo, mock_pool):
        stream_id = uuid4()
        after_id = 50
        limit = 100
        expected_rows = [{"id": 51, "event_type": "type", "payload": {}, "created_at": "2021-01-01"}]
        mock_pool.fetch = AsyncMock(return_value=expected_rows)

        events = await event_repo.get_stream(stream_id, limit, after_id)

        expected_sql = """
                SELECT id, event_type, payload, created_at
                FROM events
                WHERE stream_id = $1 AND id > $2
                ORDER BY created_at ASC
                LIMIT $3
                """
        mock_pool.fetch.assert_awaited_once_with(expected_sql, stream_id, after_id, limit)
        assert len(events) == 1

    @pytest.mark.asyncio
    async def test_get_stream_limit_zero(self, event_repo, mock_pool):
        stream_id = uuid4()
        limit = 0
        mock_pool.fetch = AsyncMock(side_effect=asyncpg.exceptions.InvalidParameterValueError("LIMIT 0"))

        with pytest.raises(asyncpg.exceptions.InvalidParameterValueError):
            await event_repo.get_stream(stream_id, limit)

    @pytest.mark.asyncio
    async def test_get_stream_empty_result(self, event_repo, mock_pool):
        stream_id = uuid4()
        mock_pool.fetch = AsyncMock(return_value=[])

        events = await event_repo.get_stream(stream_id)
        assert events == []

    @pytest.mark.asyncio
    async def test_get_stream_connection_error(self, event_repo, mock_pool):
        stream_id = uuid4()
        mock_pool.fetch = AsyncMock(side_effect=asyncpg.exceptions.ConnectionDoesNotExistError("conn"))

        with pytest.raises(asyncpg.exceptions.ConnectionDoesNotExistError):
            await event_repo.get_stream(stream_id)

    @pytest.mark.asyncio
    async def test_get_by_type_success(self, event_repo, mock_pool):
        project_id = uuid4()
        event_type = "ai_replied"
        limit = 100
        expected_rows = [
            {"id": 1, "stream_id": uuid4(), "payload": {"a": 1}, "created_at": "2021-01-01"},
        ]
        mock_pool.fetch = AsyncMock(return_value=expected_rows)

        events = await event_repo.get_by_type(project_id, event_type, limit)

        expected_sql = """
            SELECT id, stream_id, payload, created_at
            FROM events
            WHERE project_id = $1 AND event_type = $2
            ORDER BY created_at DESC
            LIMIT $3
            """
        mock_pool.fetch.assert_awaited_once_with(expected_sql, project_id, event_type, limit)
        assert len(events) == 1
        assert events[0]["id"] == 1
        assert events[0]["stream_id"] == expected_rows[0]["stream_id"]
        assert events[0]["payload"] == {"a": 1}
        assert events[0]["ts"] == "2021-01-01"

    @pytest.mark.asyncio
    async def test_get_by_type_limit_zero(self, event_repo, mock_pool):
        project_id = uuid4()
        event_type = "type"
        limit = 0
        mock_pool.fetch = AsyncMock(side_effect=asyncpg.exceptions.InvalidParameterValueError("LIMIT 0"))

        with pytest.raises(asyncpg.exceptions.InvalidParameterValueError):
            await event_repo.get_by_type(project_id, event_type, limit)

    @pytest.mark.asyncio
    async def test_get_by_type_empty_result(self, event_repo, mock_pool):
        project_id = uuid4()
        event_type = "type"
        mock_pool.fetch = AsyncMock(return_value=[])

        events = await event_repo.get_by_type(project_id, event_type)
        assert events == []

    @pytest.mark.asyncio
    async def test_get_events_for_thread_success(self, event_repo, mock_pool):
        thread_id = str(uuid4())
        limit = 30
        offset = 0
        expected_rows = [
            {"id": 1, "event_type": "type1", "payload": {"a": 1}, "created_at": "2021-01-01"},
        ]
        mock_pool.mock_conn.fetch = AsyncMock(return_value=expected_rows)

        events = await event_repo.get_events_for_thread(thread_id, limit, offset)

        mock_pool.acquire.assert_called_once()
        expected_sql = """
                SELECT id, event_type, payload, created_at
                FROM events
                WHERE stream_id = $1
                ORDER BY created_at DESC
                LIMIT $2 OFFSET $3
                """
        mock_pool.mock_conn.fetch.assert_awaited_once_with(
            expected_sql, UUID(thread_id), limit, offset
        )
        assert len(events) == 1
        assert events[0]["id"] == 1
        assert events[0]["type"] == "type1"
        assert events[0]["payload"] == {"a": 1}
        assert events[0]["ts"] == "2021-01-01"

    @pytest.mark.asyncio
    async def test_get_events_for_thread_invalid_uuid(self, event_repo, mock_pool):
        with pytest.raises(ValueError):
            await event_repo.get_events_for_thread("not-a-uuid")

    @pytest.mark.asyncio
    async def test_get_events_for_thread_limit_zero(self, event_repo, mock_pool):
        thread_id = str(uuid4())
        limit = 0
        mock_pool.mock_conn.fetch = AsyncMock(side_effect=asyncpg.exceptions.InvalidParameterValueError("LIMIT 0"))
        with pytest.raises(asyncpg.exceptions.InvalidParameterValueError):
            await event_repo.get_events_for_thread(thread_id, limit)

    @pytest.mark.asyncio
    async def test_get_events_for_thread_negative_offset(self, event_repo, mock_pool):
        thread_id = str(uuid4())
        offset = -1
        mock_pool.mock_conn.fetch = AsyncMock(side_effect=asyncpg.exceptions.InvalidParameterValueError("OFFSET -1"))
        with pytest.raises(asyncpg.exceptions.InvalidParameterValueError):
            await event_repo.get_events_for_thread(thread_id, offset=offset)

    @pytest.mark.asyncio
    async def test_get_events_for_thread_empty_result(self, event_repo, mock_pool):
        thread_id = str(uuid4())
        mock_pool.mock_conn.fetch = AsyncMock(return_value=[])
        events = await event_repo.get_events_for_thread(thread_id)
        assert events == []

    @pytest.mark.asyncio
    async def test_get_events_for_thread_connection_error(self, event_repo, mock_pool):
        thread_id = str(uuid4())
        mock_pool.mock_conn.fetch = AsyncMock(side_effect=asyncpg.exceptions.ConnectionDoesNotExistError("conn"))
        with pytest.raises(asyncpg.exceptions.ConnectionDoesNotExistError):
            await event_repo.get_events_for_thread(thread_id)


async def test_get_manager_reply_history_filters_by_project_and_manager(mock_pool):
    from src.infrastructure.db.repositories.event_repository import EventRepository

    repo = EventRepository(mock_pool)
    rows = [
        {
            "id": 1,
            "stream_id": "thread-1",
            "project_id": "project-1",
            "payload": {
                "manager_user_id": "manager-1",
                "text": "Ответ",
                "manager_transport": {"chat_id": "123"},
            },
            "created_at": "2026-04-27T12:00:00",
        }
    ]
    mock_pool.fetch.return_value = rows

    result = await repo.get_manager_reply_history(
        project_id="project-1",
        manager_user_id="manager-1",
        limit=30,
        offset=0,
    )

    assert len(result) == 1
    assert result[0].manager_user_id == "manager-1"
    assert result[0].text == "Ответ"
    mock_pool.fetch.assert_awaited_once()
