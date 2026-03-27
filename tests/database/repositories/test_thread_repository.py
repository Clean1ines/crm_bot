import pytest
from unittest.mock import AsyncMock, MagicMock, call, ANY
from uuid import UUID, uuid4
from datetime import datetime
import asyncpg

from src.database.repositories.thread_repository import ThreadRepository
from src.database.models import ThreadStatus


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
    async def test_get_or_create_client_insert(self, thread_repo, mock_pool):
        project_id = str(uuid4())
        chat_id = 12345
        username = "testuser"
        source = "telegram"
        expected_id = uuid4()
        mock_pool.mock_conn.fetchrow = AsyncMock(return_value={"id": expected_id})

        result = await thread_repo.get_or_create_client(project_id, chat_id, username, source)

        expected_sql = """
                INSERT INTO clients (project_id, chat_id, username, source)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (project_id, chat_id) DO UPDATE SET username = EXCLUDED.username
                RETURNING id
            """
        mock_pool.mock_conn.fetchrow.assert_awaited_once_with(
            expected_sql, UUID(project_id), chat_id, username, source
        )
        assert result == str(expected_id)

    @pytest.mark.asyncio
    async def test_get_or_create_client_update_on_conflict(self, thread_repo, mock_pool):
        project_id = str(uuid4())
        chat_id = 12345
        username = "new_username"
        source = "telegram"
        expected_id = uuid4()
        mock_pool.mock_conn.fetchrow = AsyncMock(return_value={"id": expected_id})

        result = await thread_repo.get_or_create_client(project_id, chat_id, username, source)

        expected_sql = """
                INSERT INTO clients (project_id, chat_id, username, source)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (project_id, chat_id) DO UPDATE SET username = EXCLUDED.username
                RETURNING id
            """
        mock_pool.mock_conn.fetchrow.assert_awaited_once_with(
            expected_sql, UUID(project_id), chat_id, username, source
        )
        assert result == str(expected_id)

    @pytest.mark.asyncio
    async def test_get_or_create_client_username_none(self, thread_repo, mock_pool):
        project_id = str(uuid4())
        chat_id = 12345
        expected_id = uuid4()
        mock_pool.mock_conn.fetchrow = AsyncMock(return_value={"id": expected_id})

        result = await thread_repo.get_or_create_client(project_id, chat_id, username=None, source="telegram")

        expected_sql = """
                INSERT INTO clients (project_id, chat_id, username, source)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (project_id, chat_id) DO UPDATE SET username = EXCLUDED.username
                RETURNING id
            """
        mock_pool.mock_conn.fetchrow.assert_awaited_once_with(
            expected_sql, UUID(project_id), chat_id, None, "telegram"
        )
        assert result == str(expected_id)

    @pytest.mark.asyncio
    async def test_get_or_create_client_invalid_uuid(self, thread_repo):
        with pytest.raises(ValueError):
            await thread_repo.get_or_create_client("invalid-uuid", 12345)

    @pytest.mark.asyncio
    async def test_get_or_create_client_fk_error(self, thread_repo, mock_pool):
        mock_pool.mock_conn.fetchrow = AsyncMock(side_effect=asyncpg.exceptions.ForeignKeyViolationError("fk"))
        with pytest.raises(asyncpg.exceptions.ForeignKeyViolationError):
            await thread_repo.get_or_create_client(str(uuid4()), 12345)

    # ------------------------------------------------------------------
    # get_active_thread
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_get_active_thread_found(self, thread_repo, mock_pool):
        client_id = str(uuid4())
        thread_id = uuid4()
        mock_pool.mock_conn.fetchrow = AsyncMock(return_value={"id": thread_id})

        result = await thread_repo.get_active_thread(client_id)

        expected_sql = """
                SELECT id FROM threads 
                WHERE client_id = $1
                ORDER BY updated_at DESC LIMIT 1
            """
        mock_pool.mock_conn.fetchrow.assert_awaited_once_with(expected_sql, UUID(client_id))
        assert result == str(thread_id)

    @pytest.mark.asyncio
    async def test_get_active_thread_not_found(self, thread_repo, mock_pool):
        mock_pool.mock_conn.fetchrow = AsyncMock(return_value=None)
        result = await thread_repo.get_active_thread(str(uuid4()))
        assert result is None

    @pytest.mark.asyncio
    async def test_get_active_thread_invalid_uuid(self, thread_repo):
        with pytest.raises(ValueError):
            await thread_repo.get_active_thread("invalid-uuid")

    # ------------------------------------------------------------------
    # create_thread
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_create_thread_success(self, thread_repo, mock_pool):
        client_id = str(uuid4())
        thread_id = uuid4()
        mock_pool.mock_conn.fetchrow = AsyncMock(return_value={"id": thread_id})

        result = await thread_repo.create_thread(client_id)

        expected_sql = """
                INSERT INTO threads (client_id, status) VALUES ($1, $2) RETURNING id
            """
        mock_pool.mock_conn.fetchrow.assert_awaited_once_with(
            expected_sql, UUID(client_id), ThreadStatus.ACTIVE.value
        )
        assert result == str(thread_id)

    @pytest.mark.asyncio
    async def test_create_thread_fk_error(self, thread_repo, mock_pool):
        mock_pool.mock_conn.fetchrow = AsyncMock(side_effect=asyncpg.exceptions.ForeignKeyViolationError("fk"))
        with pytest.raises(asyncpg.exceptions.ForeignKeyViolationError):
            await thread_repo.create_thread(str(uuid4()))

    # ------------------------------------------------------------------
    # add_message
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_add_message_success(self, thread_repo, mock_pool):
        thread_id = str(uuid4())
        role = "user"
        content = "Hello"
        mock_pool.mock_conn.execute = AsyncMock()

        await thread_repo.add_message(thread_id, role, content)

        assert mock_pool.acquire.call_count == 1
        assert mock_pool.mock_conn.execute.call_count == 2
        expected_insert_sql = """
                INSERT INTO messages (thread_id, role, content)
                VALUES ($1, $2, $3)
            """
        mock_pool.mock_conn.execute.assert_any_call(expected_insert_sql, UUID(thread_id), role, content)
        expected_update_sql = "UPDATE threads SET updated_at = NOW() WHERE id = $1"
        mock_pool.mock_conn.execute.assert_any_call(expected_update_sql, UUID(thread_id))

    @pytest.mark.asyncio
    async def test_add_message_fk_error(self, thread_repo, mock_pool):
        mock_pool.mock_conn.execute = AsyncMock(side_effect=asyncpg.exceptions.ForeignKeyViolationError("fk"))
        with pytest.raises(asyncpg.exceptions.ForeignKeyViolationError):
            await thread_repo.add_message(str(uuid4()), "user", "text")

    @pytest.mark.asyncio
    async def test_add_message_not_null_error(self, thread_repo, mock_pool):
        mock_pool.mock_conn.execute = AsyncMock(side_effect=asyncpg.exceptions.NotNullViolationError("null"))
        with pytest.raises(asyncpg.exceptions.NotNullViolationError):
            await thread_repo.add_message(str(uuid4()), None, "text")

    # ------------------------------------------------------------------
    # get_messages_for_langgraph
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_get_messages_for_langgraph_success(self, thread_repo, mock_pool):
        thread_id = str(uuid4())
        rows = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"}
        ]
        mock_pool.mock_conn.fetch = AsyncMock(return_value=rows)

        result = await thread_repo.get_messages_for_langgraph(thread_id)

        expected_sql = """
                SELECT role, content FROM messages 
                WHERE thread_id = $1 ORDER BY created_at ASC
            """
        mock_pool.mock_conn.fetch.assert_awaited_once_with(expected_sql, UUID(thread_id))
        assert len(result) == len(rows)
        assert result[0]["role"] == "user"
        assert result[1]["role"] == "assistant"

    @pytest.mark.asyncio
    async def test_get_messages_for_langgraph_empty(self, thread_repo, mock_pool):
        mock_pool.mock_conn.fetch = AsyncMock(return_value=[])
        result = await thread_repo.get_messages_for_langgraph(str(uuid4()))
        assert result == []

    # ------------------------------------------------------------------
    # update_status
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_update_status_success(self, thread_repo, mock_pool):
        thread_id = str(uuid4())
        status = ThreadStatus.MANUAL
        mock_pool.mock_conn.execute = AsyncMock()

        await thread_repo.update_status(thread_id, status)

        expected_sql = """
                UPDATE threads
                SET status = $1, updated_at = NOW()
                WHERE id = $2
            """
        mock_pool.mock_conn.execute.assert_awaited_once_with(
            expected_sql, status.value, UUID(thread_id)
        )

    @pytest.mark.asyncio
    async def test_update_status_not_found(self, thread_repo, mock_pool):
        mock_pool.mock_conn.execute = AsyncMock()
        await thread_repo.update_status(str(uuid4()), ThreadStatus.ACTIVE)
        # No error, update just does nothing
        mock_pool.mock_conn.execute.assert_awaited_once()

    # ------------------------------------------------------------------
    # update_manager_chat
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_update_manager_chat_success(self, thread_repo, mock_pool):
        thread_id = str(uuid4())
        manager_chat_id = "12345"
        mock_pool.mock_conn.execute = AsyncMock()

        await thread_repo.update_manager_chat(thread_id, manager_chat_id)

        expected_sql = """
                UPDATE threads
                SET manager_chat_id = $1, updated_at = NOW()
                WHERE id = $2
            """
        mock_pool.mock_conn.execute.assert_awaited_once_with(
            expected_sql, manager_chat_id, UUID(thread_id)
        )

    # ------------------------------------------------------------------
    # find_by_manager_chat
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_find_by_manager_chat_success(self, thread_repo, mock_pool):
        manager_chat_id = "12345"
        rows = [
            {"id": uuid4(), "client_id": uuid4(), "status": "manual", "manager_chat_id": "12345", "created_at": datetime.now(), "updated_at": datetime.now()},
            {"id": uuid4(), "client_id": uuid4(), "status": "manual", "manager_chat_id": "12345", "created_at": datetime.now(), "updated_at": datetime.now()}
        ]
        mock_pool.mock_conn.fetch = AsyncMock(return_value=rows)

        result = await thread_repo.find_by_manager_chat(manager_chat_id)

        expected_sql = """
                SELECT id, client_id, status, manager_chat_id, created_at, updated_at
                FROM threads
                WHERE manager_chat_id = $1 AND status = 'manual'
                ORDER BY updated_at DESC
            """
        mock_pool.mock_conn.fetch.assert_awaited_once_with(expected_sql, manager_chat_id)
        assert len(result) == len(rows)

    @pytest.mark.asyncio
    async def test_find_by_manager_chat_empty(self, thread_repo, mock_pool):
        mock_pool.mock_conn.fetch = AsyncMock(return_value=[])
        result = await thread_repo.find_by_manager_chat("12345")
        assert result == []

    # ------------------------------------------------------------------
    # get_thread_with_project
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_get_thread_with_project_success(self, thread_repo, mock_pool):
        thread_id = str(uuid4())
        row = {
            "id": thread_id,
            "client_id": uuid4(),
            "status": "active",
            "manager_chat_id": None,
            "context_summary": "summary",
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
            "project_id": uuid4()
        }
        mock_pool.mock_conn.fetchrow = AsyncMock(return_value=row)

        result = await thread_repo.get_thread_with_project(thread_id)

        expected_sql = """
                SELECT 
                    t.id, t.client_id, t.status, t.manager_chat_id, 
                    t.context_summary, t.created_at, t.updated_at,
                    c.project_id
                FROM threads t
                JOIN clients c ON t.client_id = c.id
                WHERE t.id = $1
            """
        mock_pool.mock_conn.fetchrow.assert_awaited_once_with(expected_sql, UUID(thread_id))
        assert result is not None
        assert result["id"] == str(row["id"])
        # FIXED: compare UUID directly
        assert result["project_id"] == row["project_id"]

    @pytest.mark.asyncio
    async def test_get_thread_with_project_not_found(self, thread_repo, mock_pool):
        mock_pool.mock_conn.fetchrow = AsyncMock(return_value=None)
        result = await thread_repo.get_thread_with_project(str(uuid4()))
        assert result is None

    # ------------------------------------------------------------------
    # update_summary
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_update_summary_success(self, thread_repo, mock_pool):
        thread_id = str(uuid4())
        summary = "new summary"
        mock_pool.mock_conn.execute = AsyncMock()

        await thread_repo.update_summary(thread_id, summary)

        expected_sql = """
                UPDATE threads
                SET context_summary = $1, updated_at = NOW()
                WHERE id = $2
            """
        mock_pool.mock_conn.execute.assert_awaited_once_with(expected_sql, summary, UUID(thread_id))

    # ------------------------------------------------------------------
    # get_state_json
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_get_state_json_success(self, thread_repo, mock_pool):
        thread_id = str(uuid4())
        state = {"key": "value"}
        row = {"state_json": state}
        mock_pool.mock_conn.fetchrow = AsyncMock(return_value=row)

        result = await thread_repo.get_state_json(thread_id)

        expected_sql = """
                SELECT state_json FROM threads WHERE id = $1
            """
        mock_pool.mock_conn.fetchrow.assert_awaited_once_with(expected_sql, UUID(thread_id))
        assert result == state

    @pytest.mark.asyncio
    async def test_get_state_json_none(self, thread_repo, mock_pool):
        mock_pool.mock_conn.fetchrow = AsyncMock(return_value={"state_json": None})
        result = await thread_repo.get_state_json(str(uuid4()))
        assert result is None

    @pytest.mark.asyncio
    async def test_get_state_json_not_found(self, thread_repo, mock_pool):
        mock_pool.mock_conn.fetchrow = AsyncMock(return_value=None)
        result = await thread_repo.get_state_json(str(uuid4()))
        assert result is None

    # ------------------------------------------------------------------
    # save_state_json
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_save_state_json_success(self, thread_repo, mock_pool):
        thread_id = str(uuid4())
        state = {"key": "value"}
        mock_pool.mock_conn.execute = AsyncMock()

        await thread_repo.save_state_json(thread_id, state)

        expected_sql = """
                UPDATE threads
                SET state_json = $1, updated_at = NOW()
                WHERE id = $2
            """
        mock_pool.mock_conn.execute.assert_awaited_once_with(
            expected_sql, '{"key": "value"}', UUID(thread_id)
        )

    # ------------------------------------------------------------------
    # update_analytics
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_update_analytics_single_field(self, thread_repo, mock_pool):
        thread_id = str(uuid4())
        intent = "pricing"
        mock_pool.mock_conn.execute = AsyncMock()

        await thread_repo.update_analytics(thread_id, intent=intent)

        expected_sql = """
            UPDATE threads
            SET intent = $1, updated_at = NOW()
            WHERE id = $2
        """
        mock_pool.mock_conn.execute.assert_awaited_once_with(
            expected_sql, intent, UUID(thread_id)
        )

    @pytest.mark.asyncio
    async def test_update_analytics_multiple_fields(self, thread_repo, mock_pool):
        thread_id = str(uuid4())
        intent = "support"
        lifecycle = "warm"
        cta = "call_manager"
        decision = "ESCALATE"
        mock_pool.mock_conn.execute = AsyncMock()

        await thread_repo.update_analytics(thread_id, intent=intent, lifecycle=lifecycle, cta=cta, decision=decision)

        expected_sql = """
            UPDATE threads
            SET intent = $1, lifecycle = $2, cta = $3, decision = $4, updated_at = NOW()
            WHERE id = $5
        """
        mock_pool.mock_conn.execute.assert_awaited_once_with(
            expected_sql, intent, lifecycle, cta, decision, UUID(thread_id)
        )

    @pytest.mark.asyncio
    async def test_update_analytics_no_fields(self, thread_repo, mock_pool):
        mock_pool.mock_conn.execute = AsyncMock()
        await thread_repo.update_analytics(str(uuid4()))
        mock_pool.mock_conn.execute.assert_not_called()

    # ------------------------------------------------------------------
    # get_analytics
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_get_analytics_success(self, thread_repo, mock_pool):
        thread_id = str(uuid4())
        row = {"intent": "pricing", "lifecycle": "cold", "cta": None, "decision": "LLM_GENERATE"}
        mock_pool.mock_conn.fetchrow = AsyncMock(return_value=row)

        result = await thread_repo.get_analytics(thread_id)

        expected_sql = """
                SELECT intent, lifecycle, cta, decision
                FROM threads
                WHERE id = $1
            """
        mock_pool.mock_conn.fetchrow.assert_awaited_once_with(expected_sql, UUID(thread_id))
        assert result == row

    @pytest.mark.asyncio
    async def test_get_analytics_not_found(self, thread_repo, mock_pool):
        mock_pool.mock_conn.fetchrow = AsyncMock(return_value=None)
        result = await thread_repo.get_analytics(str(uuid4()))
        assert result is None

    # ------------------------------------------------------------------
    # get_message_counts
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_get_message_counts_success(self, thread_repo, mock_pool):
        thread_id = str(uuid4())
        row = {"total": 5, "ai": 3, "manager": 2}
        mock_pool.mock_conn.fetchrow = AsyncMock(return_value=row)

        result = await thread_repo.get_message_counts(thread_id)

        expected_sql = """
                SELECT 
                    COUNT(*) as total,
                    COUNT(CASE WHEN role = 'assistant' THEN 1 END) as ai,
                    COUNT(CASE WHEN role = 'user' THEN 1 END) as manager  -- manager messages are 'user' role from manager bot
                FROM messages
                WHERE thread_id = $1
            """
        mock_pool.mock_conn.fetchrow.assert_awaited_once_with(expected_sql, UUID(thread_id))
        assert result == row

    @pytest.mark.asyncio
    async def test_get_message_counts_empty(self, thread_repo, mock_pool):
        row = {"total": 0, "ai": 0, "manager": 0}
        mock_pool.mock_conn.fetchrow = AsyncMock(return_value=row)
        result = await thread_repo.get_message_counts(str(uuid4()))
        assert result == row

    # ------------------------------------------------------------------
    # get_dialogs
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_get_dialogs_success(self, thread_repo, mock_pool):
        project_id = str(uuid4())
        limit = 20
        offset = 0
        rows = [
            {
                "thread_id": uuid4(),
                "status": "active",
                "interaction_mode": "normal",
                "thread_created_at": datetime(2025, 1, 1, 12, 0),
                "thread_updated_at": datetime(2025, 1, 2, 12, 0),
                "client_id": uuid4(),
                "full_name": "John Doe",
                "username": "johndoe",
                "chat_id": 12345,
                "last_message_content": "Hello",
                "last_message_created_at": datetime(2025, 1, 2, 12, 0)
            }
        ]
        mock_pool.mock_conn.fetch = AsyncMock(return_value=rows)

        result = await thread_repo.get_dialogs(project_id, limit, offset)

        # Build expected SQL with where clause: c.project_id = $1
        expected_sql = """
            SELECT
                t.id AS thread_id,
                t.status,
                t.interaction_mode,
                t.created_at AS thread_created_at,
                t.updated_at AS thread_updated_at,
                c.id AS client_id,
                c.full_name,
                c.username,
                c.chat_id,
                lm.content AS last_message_content,
                lm.created_at AS last_message_created_at
            FROM threads t
            JOIN clients c ON t.client_id = c.id
            LEFT JOIN LATERAL (
                SELECT content, created_at
                FROM messages m
                WHERE m.thread_id = t.id
                ORDER BY m.created_at DESC
                LIMIT 1
            ) lm ON true
            WHERE c.project_id = $1
            ORDER BY t.updated_at DESC
            LIMIT $2 OFFSET $3
        """
        mock_pool.mock_conn.fetch.assert_awaited_once_with(
            expected_sql, UUID(project_id), limit, offset
        )
        assert len(result) == 1
        assert result[0]["thread_id"] == str(rows[0]["thread_id"])
        assert result[0]["client"]["id"] == str(rows[0]["client_id"])
        assert result[0]["last_message"]["content"] == "Hello"
        # Check datetime conversion
        assert result[0]["thread_created_at"] == rows[0]["thread_created_at"].isoformat()
        assert result[0]["last_message"]["created_at"] == rows[0]["last_message_created_at"].isoformat()

    @pytest.mark.asyncio
    async def test_get_dialogs_with_status_filter(self, thread_repo, mock_pool):
        project_id = str(uuid4())
        status_filter = "active"
        limit = 20
        offset = 0
        mock_pool.mock_conn.fetch = AsyncMock(return_value=[])

        await thread_repo.get_dialogs(project_id, limit, offset, status_filter=status_filter)

        expected_sql = """
            SELECT
                t.id AS thread_id,
                t.status,
                t.interaction_mode,
                t.created_at AS thread_created_at,
                t.updated_at AS thread_updated_at,
                c.id AS client_id,
                c.full_name,
                c.username,
                c.chat_id,
                lm.content AS last_message_content,
                lm.created_at AS last_message_created_at
            FROM threads t
            JOIN clients c ON t.client_id = c.id
            LEFT JOIN LATERAL (
                SELECT content, created_at
                FROM messages m
                WHERE m.thread_id = t.id
                ORDER BY m.created_at DESC
                LIMIT 1
            ) lm ON true
            WHERE c.project_id = $1 AND t.status = $2
            ORDER BY t.updated_at DESC
            LIMIT $3 OFFSET $4
        """
        mock_pool.mock_conn.fetch.assert_awaited_once_with(
            expected_sql, UUID(project_id), status_filter, limit, offset
        )

    @pytest.mark.asyncio
    async def test_get_dialogs_with_search(self, thread_repo, mock_pool):
        project_id = str(uuid4())
        search = "john"
        limit = 20
        offset = 0
        mock_pool.mock_conn.fetch = AsyncMock(return_value=[])

        await thread_repo.get_dialogs(project_id, limit, offset, search=search)

        expected_sql = """
            SELECT
                t.id AS thread_id,
                t.status,
                t.interaction_mode,
                t.created_at AS thread_created_at,
                t.updated_at AS thread_updated_at,
                c.id AS client_id,
                c.full_name,
                c.username,
                c.chat_id,
                lm.content AS last_message_content,
                lm.created_at AS last_message_created_at
            FROM threads t
            JOIN clients c ON t.client_id = c.id
            LEFT JOIN LATERAL (
                SELECT content, created_at
                FROM messages m
                WHERE m.thread_id = t.id
                ORDER BY m.created_at DESC
                LIMIT 1
            ) lm ON true
            WHERE c.project_id = $1 AND (c.full_name ILIKE $$2 OR c.username ILIKE $$2)
            ORDER BY t.updated_at DESC
            LIMIT $3 OFFSET $4
        """
        mock_pool.mock_conn.fetch.assert_awaited_once_with(
            expected_sql, UUID(project_id), f"%{search}%", limit, offset
        )

    @pytest.mark.asyncio
    async def test_get_dialogs_limit_zero(self, thread_repo, mock_pool):
        mock_pool.mock_conn.fetch = AsyncMock(side_effect=asyncpg.exceptions.InvalidParameterValueError("LIMIT 0"))
        with pytest.raises(asyncpg.exceptions.InvalidParameterValueError):
            await thread_repo.get_dialogs(str(uuid4()), limit=0)

    @pytest.mark.asyncio
    async def test_get_dialogs_empty(self, thread_repo, mock_pool):
        mock_pool.mock_conn.fetch = AsyncMock(return_value=[])
        result = await thread_repo.get_dialogs(str(uuid4()))
        assert result == []

    # ------------------------------------------------------------------
    # get_messages
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_get_messages_success(self, thread_repo, mock_pool):
        thread_id = str(uuid4())
        limit = 20
        offset = 0
        rows = [
            {"id": uuid4(), "role": "user", "content": "Hello", "created_at": datetime(2025, 1, 1, 12, 0), "metadata": {"x": 1}},
            {"id": uuid4(), "role": "assistant", "content": "Hi", "created_at": datetime(2025, 1, 1, 12, 1), "metadata": {}}
        ]
        mock_pool.mock_conn.fetch = AsyncMock(return_value=rows)

        result = await thread_repo.get_messages(thread_id, limit, offset)

        expected_sql = """
                SELECT id, role, content, created_at, metadata
                FROM messages
                WHERE thread_id = $1
                ORDER BY created_at DESC
                LIMIT $2 OFFSET $3
            """
        mock_pool.mock_conn.fetch.assert_awaited_once_with(
            expected_sql, UUID(thread_id), limit, offset
        )
        # Messages are reversed to chronological order
        assert len(result) == 2
        assert result[0]["role"] == "assistant"  # because reversed
        assert result[0]["content"] == "Hi"
        assert result[1]["role"] == "user"
        assert result[1]["content"] == "Hello"

    @pytest.mark.asyncio
    async def test_get_messages_empty(self, thread_repo, mock_pool):
        mock_pool.mock_conn.fetch = AsyncMock(return_value=[])
        result = await thread_repo.get_messages(str(uuid4()))
        assert result == []

    @pytest.mark.asyncio
    async def test_get_messages_limit_zero(self, thread_repo, mock_pool):
        mock_pool.mock_conn.fetch = AsyncMock(side_effect=asyncpg.exceptions.InvalidParameterValueError("LIMIT 0"))
        with pytest.raises(asyncpg.exceptions.InvalidParameterValueError):
            await thread_repo.get_messages(str(uuid4()), limit=0)

    # ------------------------------------------------------------------
    # update_interaction_mode
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_update_interaction_mode_success(self, thread_repo, mock_pool):
        thread_id = str(uuid4())
        mode = "demo"
        mock_pool.mock_conn.execute = AsyncMock()

        await thread_repo.update_interaction_mode(thread_id, mode)

        expected_sql = """
                UPDATE threads
                SET interaction_mode = $1, updated_at = NOW()
                WHERE id = $2
            """
        mock_pool.mock_conn.execute.assert_awaited_once_with(expected_sql, mode, UUID(thread_id))

    # ------------------------------------------------------------------
    # find_by_status
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
                SELECT t.*, c.name as client_name
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
