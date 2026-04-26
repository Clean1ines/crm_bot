import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import asyncpg
import pytest

from src.domain.project_plane.manager_assignments import ManagerActor
from src.domain.project_plane.thread_status import ThreadStatus
from src.domain.project_plane.thread_views import (
    ThreadAnalyticsView,
    ThreadDialogView,
    ThreadMessageCounts,
    ThreadMessageView,
    ThreadRuntimeMessageView,
    ThreadStatusSummaryView,
    ThreadWithProjectView,
)
from src.infrastructure.db.repositories.thread_repository import ThreadRepository


class MockAcquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.fixture
def mock_conn():
    conn = AsyncMock()
    conn.fetch = AsyncMock()
    conn.fetchrow = AsyncMock()
    conn.execute = AsyncMock()
    conn.transaction = MagicMock()
    return conn


@pytest.fixture
def mock_pool(mock_conn):
    pool = MagicMock()
    pool.acquire.return_value = MockAcquire(mock_conn)
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
    async def test_get_or_create_client_inserts_or_updates_project_scoped_client(self, thread_repo, mock_conn):
        project_id = uuid4()
        client_id = uuid4()
        mock_conn.fetchrow.return_value = {"id": client_id}

        result = await thread_repo.get_or_create_client(
            project_id=str(project_id),
            chat_id=12345,
            username="client_username",
            source="telegram",
            full_name="Client Name",
        )

        expected_sql = """
                INSERT INTO clients (project_id, chat_id, username, source, user_id, full_name)
                VALUES (
                    $1,
                    $2,
                    $3,
                    $4,
                    (SELECT id FROM users WHERE telegram_id = $2 LIMIT 1),
                    $5
                )
                ON CONFLICT (project_id, chat_id) DO UPDATE
                SET
                    username = EXCLUDED.username,
                    full_name = COALESCE(EXCLUDED.full_name, clients.full_name),
                    user_id = COALESCE(clients.user_id, EXCLUDED.user_id)
                RETURNING id
            """
        mock_conn.fetchrow.assert_awaited_once_with(
            expected_sql,
            UUID(str(project_id)),
            12345,
            "client_username",
            "telegram",
            "Client Name",
        )
        assert result == str(client_id)

    @pytest.mark.asyncio
    async def test_get_or_create_client_invalid_project_uuid_raises(self, thread_repo):
        with pytest.raises(ValueError):
            await thread_repo.get_or_create_client("not-a-uuid", 12345)

    # ------------------------------------------------------------------
    # get_active_thread
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_get_active_thread_returns_latest_thread_id(self, thread_repo, mock_conn):
        client_id = uuid4()
        thread_id = uuid4()
        mock_conn.fetchrow.return_value = {"id": thread_id}

        result = await thread_repo.get_active_thread(str(client_id))

        expected_sql = """
                SELECT id FROM threads 
                WHERE client_id = $1
                ORDER BY updated_at DESC LIMIT 1
            """
        mock_conn.fetchrow.assert_awaited_once_with(expected_sql, UUID(str(client_id)))
        assert result == str(thread_id)

    @pytest.mark.asyncio
    async def test_get_active_thread_returns_none_when_missing(self, thread_repo, mock_conn):
        mock_conn.fetchrow.return_value = None

        result = await thread_repo.get_active_thread(str(uuid4()))

        assert result is None

    # ------------------------------------------------------------------
    # create_thread
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_create_thread_uses_active_status(self, thread_repo, mock_conn):
        client_id = uuid4()
        thread_id = uuid4()
        mock_conn.fetchrow.return_value = {"id": thread_id}

        result = await thread_repo.create_thread(str(client_id))

        expected_sql = """
                INSERT INTO threads (client_id, status) VALUES ($1, $2) RETURNING id
            """
        mock_conn.fetchrow.assert_awaited_once_with(
            expected_sql,
            UUID(str(client_id)),
            ThreadStatus.ACTIVE.value,
        )
        assert result == str(thread_id)

    # ------------------------------------------------------------------
    # add_message
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_add_message_inserts_message_and_refreshes_thread_timestamp(self, thread_repo, mock_conn):
        thread_id = uuid4()

        await thread_repo.add_message(str(thread_id), role="user", content="hello")

        insert_sql = """
                INSERT INTO messages (thread_id, role, content)
                VALUES ($1, $2, $3)
            """
        update_sql = "UPDATE threads SET updated_at = NOW() WHERE id = $1"

        assert mock_conn.execute.await_count == 2
        mock_conn.execute.assert_any_await(insert_sql, UUID(str(thread_id)), "user", "hello")
        mock_conn.execute.assert_any_await(update_sql, UUID(str(thread_id)))

    # ------------------------------------------------------------------
    # get_messages_for_langgraph
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_get_messages_for_langgraph_returns_runtime_message_views(self, thread_repo, mock_conn):
        thread_id = uuid4()
        mock_conn.fetch.return_value = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]

        result = await thread_repo.get_messages_for_langgraph(str(thread_id))

        expected_sql = """
                SELECT role, content FROM messages 
                WHERE thread_id = $1 ORDER BY created_at ASC
            """
        mock_conn.fetch.assert_awaited_once_with(expected_sql, UUID(str(thread_id)))
        assert result == [
            ThreadRuntimeMessageView(role="user", content="hello"),
            ThreadRuntimeMessageView(role="assistant", content="hi"),
        ]

    # ------------------------------------------------------------------
    # update_status
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_update_status_writes_status_value(self, thread_repo, mock_conn):
        thread_id = uuid4()

        await thread_repo.update_status(str(thread_id), ThreadStatus.CLOSED)

        expected_sql = """
                UPDATE threads
                SET status = $1, updated_at = NOW()
                WHERE id = $2
            """
        mock_conn.execute.assert_awaited_once_with(
            expected_sql,
            ThreadStatus.CLOSED.value,
            UUID(str(thread_id)),
        )

    # ------------------------------------------------------------------
    # claim_for_manager
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_claim_for_manager_uses_explicit_canonical_and_transport_ids(self, thread_repo, mock_conn):
        thread_id = uuid4()
        manager_user_id = uuid4()

        await thread_repo.claim_for_manager(
            str(thread_id),
            manager_user_id=str(manager_user_id),
            manager_chat_id="12345",
        )

        expected_sql = """
                UPDATE threads
                SET
                    status = $1,
                    manager_user_id = $2,
                    manager_chat_id = $3,
                    updated_at = NOW()
                WHERE id = $4
            """
        mock_conn.execute.assert_awaited_once_with(
            expected_sql,
            ThreadStatus.MANUAL.value,
            UUID(str(manager_user_id)),
            "12345",
            UUID(str(thread_id)),
        )

    @pytest.mark.asyncio
    async def test_claim_for_manager_accepts_manager_actor(self, thread_repo, mock_conn):
        thread_id = uuid4()
        manager_user_id = uuid4()
        manager = ManagerActor(user_id=str(manager_user_id), telegram_chat_id="777")

        await thread_repo.claim_for_manager(str(thread_id), manager=manager)

        args = mock_conn.execute.await_args.args
        assert args[1:] == (
            ThreadStatus.MANUAL.value,
            UUID(str(manager_user_id)),
            "777",
            UUID(str(thread_id)),
        )

    @pytest.mark.asyncio
    async def test_claim_for_manager_allows_transport_only_legacy_assignment(self, thread_repo, mock_conn):
        thread_id = uuid4()

        await thread_repo.claim_for_manager(str(thread_id), manager_chat_id="777")

        args = mock_conn.execute.await_args.args
        assert args[1:] == (
            ThreadStatus.MANUAL.value,
            None,
            "777",
            UUID(str(thread_id)),
        )

    # ------------------------------------------------------------------
    # release_manager_assignment
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_release_manager_assignment_returns_thread_to_active_ai_mode(self, thread_repo, mock_conn):
        thread_id = uuid4()

        await thread_repo.release_manager_assignment(str(thread_id))

        expected_sql = """
                UPDATE threads
                SET
                    status = $1,
                    manager_user_id = NULL,
                    manager_chat_id = NULL,
                    updated_at = NOW()
                WHERE id = $2
            """
        mock_conn.execute.assert_awaited_once_with(
            expected_sql,
            ThreadStatus.ACTIVE.value,
            UUID(str(thread_id)),
        )

    # ------------------------------------------------------------------
    # get_thread_with_project_view
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_get_thread_with_project_view_returns_typed_view(self, thread_repo, mock_conn):
        thread_id = uuid4()
        client_id = uuid4()
        project_id = uuid4()
        manager_user_id = uuid4()
        created_at = datetime.now()
        updated_at = datetime.now()

        mock_conn.fetchrow.return_value = {
            "id": thread_id,
            "client_id": client_id,
            "status": "manual",
            "manager_user_id": manager_user_id,
            "manager_chat_id": "12345",
            "context_summary": "summary",
            "created_at": created_at,
            "updated_at": updated_at,
            "project_id": project_id,
            "full_name": "Client Name",
            "username": "client",
            "chat_id": 555,
        }

        result = await thread_repo.get_thread_with_project_view(str(thread_id))

        assert isinstance(result, ThreadWithProjectView)
        assert result.thread_id == str(thread_id)
        assert result.client_id == str(client_id)
        assert result.project_id == str(project_id)
        assert result.manager_user_id == str(manager_user_id)
        assert result.manager_chat_id == "12345"
        assert result.chat_id == 555

    @pytest.mark.asyncio
    async def test_get_thread_with_project_view_returns_none_when_missing(self, thread_repo, mock_conn):
        mock_conn.fetchrow.return_value = None

        result = await thread_repo.get_thread_with_project_view(str(uuid4()))

        assert result is None

    # ------------------------------------------------------------------
    # append_manager_reply_message
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_append_manager_reply_message_updates_thread_and_inserts_assistant_message_in_transaction(
        self,
        thread_repo,
        mock_conn,
    ):
        thread_id = uuid4()
        tx = AsyncMock()
        tx.__aenter__.return_value = None
        tx.__aexit__.return_value = None
        mock_conn.transaction.return_value = tx

        await thread_repo.append_manager_reply_message(str(thread_id), "manager reply")

        mock_conn.transaction.assert_called_once()
        update_sql = """
                    UPDATE threads
                    SET updated_at = NOW()
                    WHERE id = $1
                """
        insert_sql = """
                    INSERT INTO messages (thread_id, role, content)
                    VALUES ($1, $2, $3)
                """
        mock_conn.execute.assert_any_await(update_sql, UUID(str(thread_id)))
        mock_conn.execute.assert_any_await(insert_sql, UUID(str(thread_id)), "assistant", "manager reply")

    # ------------------------------------------------------------------
    # update_summary
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_update_summary_writes_context_summary(self, thread_repo, mock_conn):
        thread_id = uuid4()

        await thread_repo.update_summary(str(thread_id), "short summary")

        expected_sql = """
                UPDATE threads
                SET context_summary = $1, updated_at = NOW()
                WHERE id = $2
            """
        mock_conn.execute.assert_awaited_once_with(
            expected_sql,
            "short summary",
            UUID(str(thread_id)),
        )

    # ------------------------------------------------------------------
    # get_state_json / save_state_json
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_get_state_json_returns_existing_state(self, thread_repo, mock_conn):
        thread_id = uuid4()
        state = {"intent": "pricing"}
        mock_conn.fetchrow.return_value = {"state_json": state}

        result = await thread_repo.get_state_json(str(thread_id))

        expected_sql = """
                SELECT state_json FROM threads WHERE id = $1
            """
        mock_conn.fetchrow.assert_awaited_once_with(expected_sql, UUID(str(thread_id)))
        assert result == state

    @pytest.mark.asyncio
    async def test_get_state_json_returns_none_when_row_missing(self, thread_repo, mock_conn):
        mock_conn.fetchrow.return_value = None

        result = await thread_repo.get_state_json(str(uuid4()))

        assert result is None

    @pytest.mark.asyncio
    async def test_get_state_json_returns_none_when_state_is_null(self, thread_repo, mock_conn):
        mock_conn.fetchrow.return_value = {"state_json": None}

        result = await thread_repo.get_state_json(str(uuid4()))

        assert result is None

    @pytest.mark.asyncio
    async def test_save_state_json_serializes_utf8_json(self, thread_repo, mock_conn):
        thread_id = uuid4()
        state = {"message": "привет"}

        await thread_repo.save_state_json(str(thread_id), state)

        expected_sql = """
                UPDATE threads
                SET state_json = $1, updated_at = NOW()
                WHERE id = $2
            """
        saved_json = mock_conn.execute.await_args.args[1]
        assert json.loads(saved_json) == state
        assert "привет" in saved_json
        mock_conn.execute.assert_awaited_once_with(expected_sql, saved_json, UUID(str(thread_id)))

    # ------------------------------------------------------------------
    # update_analytics / get_analytics_view
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_update_analytics_updates_only_present_fields(self, thread_repo, mock_conn):
        thread_id = uuid4()

        await thread_repo.update_analytics(
            str(thread_id),
            intent="pricing",
            lifecycle=None,
            cta="book_call",
            decision="RESPOND_KB",
        )

        expected_sql = """
            UPDATE threads
            SET intent = $1, cta = $2, decision = $3, updated_at = NOW()
            WHERE id = $4
        """
        mock_conn.execute.assert_awaited_once_with(
            expected_sql,
            "pricing",
            "book_call",
            "RESPOND_KB",
            UUID(str(thread_id)),
        )

    @pytest.mark.asyncio
    async def test_update_analytics_no_fields_is_noop(self, thread_repo, mock_conn):
        await thread_repo.update_analytics(str(uuid4()))

        mock_conn.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_get_analytics_view_returns_typed_view(self, thread_repo, mock_conn):
        thread_id = uuid4()
        mock_conn.fetchrow.return_value = {
            "intent": "pricing",
            "lifecycle": "warm",
            "cta": "book_call",
            "decision": "RESPOND_KB",
        }

        result = await thread_repo.get_analytics_view(str(thread_id))

        assert result == ThreadAnalyticsView(
            intent="pricing",
            lifecycle="warm",
            cta="book_call",
            decision="RESPOND_KB",
        )

    @pytest.mark.asyncio
    async def test_get_analytics_view_returns_none_when_missing(self, thread_repo, mock_conn):
        mock_conn.fetchrow.return_value = None

        result = await thread_repo.get_analytics_view(str(uuid4()))

        assert result is None

    # ------------------------------------------------------------------
    # get_message_counts_view
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_get_message_counts_view_returns_typed_counts(self, thread_repo, mock_conn):
        thread_id = uuid4()
        mock_conn.fetchrow.return_value = {"total": 5, "ai": 3, "manager": 2}

        result = await thread_repo.get_message_counts_view(str(thread_id))

        assert result == ThreadMessageCounts(total=5, ai=3, manager=2)

    @pytest.mark.asyncio
    async def test_get_message_counts_view_returns_zero_counts_when_missing(self, thread_repo, mock_conn):
        mock_conn.fetchrow.return_value = None

        result = await thread_repo.get_message_counts_view(str(uuid4()))

        assert result == ThreadMessageCounts(total=0, ai=0, manager=0)

    # ------------------------------------------------------------------
    # get_dialogs
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_get_dialogs_returns_typed_dialogs_with_last_message(self, thread_repo, mock_conn):
        project_id = uuid4()
        thread_id = uuid4()
        client_id = uuid4()
        thread_created_at = datetime(2025, 1, 1, 12, 0, 0)
        thread_updated_at = datetime(2025, 1, 2, 12, 0, 0)
        last_message_created_at = datetime(2025, 1, 2, 11, 0, 0)

        mock_conn.fetch.return_value = [
            {
                "thread_id": thread_id,
                "status": "active",
                "interaction_mode": "ai",
                "thread_created_at": thread_created_at,
                "thread_updated_at": thread_updated_at,
                "client_id": client_id,
                "full_name": "Client Name",
                "username": "client",
                "chat_id": 12345,
                "last_message_content": "hello",
                "last_message_created_at": last_message_created_at,
            }
        ]

        result = await thread_repo.get_dialogs(
            str(project_id),
            limit=10,
            offset=5,
            status_filter="active",
            search="Client",
        )

        assert len(result) == 1
        dialog = result[0]
        assert isinstance(dialog, ThreadDialogView)
        assert dialog.thread_id == str(thread_id)
        assert dialog.status == "active"
        assert dialog.client.id == str(client_id)
        assert dialog.client.full_name == "Client Name"
        assert dialog.last_message is not None
        assert dialog.last_message.content == "hello"
        assert dialog.thread_created_at == thread_created_at.isoformat()
        assert dialog.thread_updated_at == thread_updated_at.isoformat()
        assert dialog.last_message.created_at == last_message_created_at.isoformat()

        sql, *params = mock_conn.fetch.await_args.args
        assert "c.project_id = $1" in sql
        assert "t.status = $2" in sql
        assert "(c.full_name ILIKE $3 OR c.username ILIKE $3)" in sql
        assert params == [UUID(str(project_id)), "active", "%Client%", 10, 5]

    @pytest.mark.asyncio
    async def test_get_dialogs_handles_missing_last_message(self, thread_repo, mock_conn):
        mock_conn.fetch.return_value = [
            {
                "thread_id": uuid4(),
                "status": "active",
                "interaction_mode": None,
                "thread_created_at": None,
                "thread_updated_at": None,
                "client_id": uuid4(),
                "full_name": None,
                "username": None,
                "chat_id": None,
                "last_message_content": None,
                "last_message_created_at": None,
            }
        ]

        result = await thread_repo.get_dialogs(str(uuid4()))

        assert result[0].last_message is None

    # ------------------------------------------------------------------
    # get_messages
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_get_messages_returns_chronological_typed_messages(self, thread_repo, mock_conn):
        thread_id = uuid4()
        first_id = uuid4()
        second_id = uuid4()
        first_created_at = datetime(2025, 1, 2, 12, 0, 0)
        second_created_at = datetime(2025, 1, 2, 11, 0, 0)

        # Repository query returns DESC, method reverses to chronological order.
        mock_conn.fetch.return_value = [
            {
                "id": first_id,
                "role": "assistant",
                "content": "newer",
                "created_at": first_created_at,
                "metadata": {"source": "ai"},
            },
            {
                "id": second_id,
                "role": "user",
                "content": "older",
                "created_at": second_created_at,
                "metadata": None,
            },
        ]

        result = await thread_repo.get_messages(str(thread_id), limit=20, offset=0)

        assert result == [
            ThreadMessageView(
                id=str(second_id),
                role="user",
                content="older",
                created_at=second_created_at.isoformat(),
                metadata={},
            ),
            ThreadMessageView(
                id=str(first_id),
                role="assistant",
                content="newer",
                created_at=first_created_at.isoformat(),
                metadata={"source": "ai"},
            ),
        ]

    # ------------------------------------------------------------------
    # update_interaction_mode
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_update_interaction_mode_writes_mode(self, thread_repo, mock_conn):
        thread_id = uuid4()

        await thread_repo.update_interaction_mode(str(thread_id), "manual")

        expected_sql = """
                UPDATE threads
                SET interaction_mode = $1, updated_at = NOW()
                WHERE id = $2
            """
        mock_conn.execute.assert_awaited_once_with(
            expected_sql,
            "manual",
            UUID(str(thread_id)),
        )

    # ------------------------------------------------------------------
    # find_by_status
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_find_by_status_returns_typed_status_summaries(self, thread_repo, mock_conn):
        status = "active"
        rows = [
            {"id": uuid4(), "client_id": uuid4(), "status": "active", "client_name": "John"},
            {"id": uuid4(), "client_id": uuid4(), "status": "active", "client_name": "Jane"},
        ]
        mock_conn.fetch.return_value = rows

        result = await thread_repo.find_by_status(status)

        expected_sql = """
                SELECT t.*, c.full_name as client_name
                FROM threads t
                JOIN clients c ON t.client_id = c.id
                WHERE t.status = $1
                ORDER BY t.updated_at DESC
            """
        mock_conn.fetch.assert_awaited_once_with(expected_sql, status)
        assert result == [
            ThreadStatusSummaryView(
                id=str(rows[0]["id"]),
                client_id=str(rows[0]["client_id"]),
                status="active",
                client_name="John",
            ),
            ThreadStatusSummaryView(
                id=str(rows[1]["id"]),
                client_id=str(rows[1]["client_id"]),
                status="active",
                client_name="Jane",
            ),
        ]

    @pytest.mark.asyncio
    async def test_find_by_status_empty(self, thread_repo, mock_conn):
        mock_conn.fetch.return_value = []

        result = await thread_repo.find_by_status("active")

        assert result == []

    # ------------------------------------------------------------------
    # Database error propagation
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_connection_error_is_not_swallowed(self, thread_repo, mock_pool):
        mock_pool.acquire.side_effect = asyncpg.exceptions.ConnectionDoesNotExistError("conn closed")

        with pytest.raises(asyncpg.exceptions.ConnectionDoesNotExistError):
            await thread_repo.get_active_thread(str(uuid4()))

    @pytest.mark.asyncio
    async def test_undefined_table_error_is_not_swallowed(self, thread_repo, mock_conn):
        mock_conn.fetch.side_effect = asyncpg.exceptions.UndefinedTableError("no table")

        with pytest.raises(asyncpg.exceptions.UndefinedTableError):
            await thread_repo.get_messages_for_langgraph(str(uuid4()))
