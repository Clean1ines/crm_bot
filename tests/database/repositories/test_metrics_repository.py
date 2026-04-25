import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call, ANY
from uuid import UUID, uuid4
from datetime import date, datetime
import asyncpg

from src.infrastructure.db.repositories.metrics_repository import MetricsRepository
from src.utils.uuid_utils import ensure_uuid


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
def metrics_repo(mock_pool):
    return MetricsRepository(mock_pool)


class TestMetricsRepository:
    def test_init(self, metrics_repo, mock_pool):
        assert metrics_repo.pool is mock_pool

    # --------------------------------------------------------------------------
    # update_thread_metrics
    # --------------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_update_thread_metrics_all_fields(self, metrics_repo, mock_pool):
        thread_id = str(uuid4())
        total_messages = 5
        ai_messages = 3
        manager_messages = 2
        escalated = True
        resolution_time = 120.5
        mock_pool.mock_conn.execute = AsyncMock()

        await metrics_repo.update_thread_metrics(
            thread_id=thread_id,
            total_messages=total_messages,
            ai_messages=ai_messages,
            manager_messages=manager_messages,
            escalated=escalated,
            resolution_time=resolution_time
        )

        assert mock_pool.acquire.call_count == 1
        expected_sql = """
            INSERT INTO thread_metrics (thread_id, total_messages, ai_messages, manager_messages, escalated, resolution_time, updated_at)
            VALUES ($1, 0, 0, 0, false, NULL, NOW())
            ON CONFLICT (thread_id) DO UPDATE SET
            total_messages = COALESCE(total_messages, 0) + $2, ai_messages = COALESCE(ai_messages, 0) + $3, manager_messages = COALESCE(manager_messages, 0) + $4, escalated = $5, resolution_time = $6 * interval '1 second', updated_at = NOW()
        """
        mock_pool.mock_conn.execute.assert_awaited_once_with(
            expected_sql,
            UUID(thread_id), total_messages, ai_messages, manager_messages, escalated, resolution_time
        )

    @pytest.mark.asyncio
    async def test_update_thread_metrics_partial_fields(self, metrics_repo, mock_pool):
        thread_id = str(uuid4())
        total_messages = 2
        escalated = False
        mock_pool.mock_conn.execute = AsyncMock()

        await metrics_repo.update_thread_metrics(
            thread_id=thread_id,
            total_messages=total_messages,
            escalated=escalated
        )

        expected_sql = """
            INSERT INTO thread_metrics (thread_id, total_messages, ai_messages, manager_messages, escalated, resolution_time, updated_at)
            VALUES ($1, 0, 0, 0, false, NULL, NOW())
            ON CONFLICT (thread_id) DO UPDATE SET
            total_messages = COALESCE(total_messages, 0) + $2, escalated = $3, updated_at = NOW()
        """
        mock_pool.mock_conn.execute.assert_awaited_once_with(
            expected_sql, UUID(thread_id), total_messages, escalated
        )

    @pytest.mark.asyncio
    async def test_update_thread_metrics_no_updates(self, metrics_repo, mock_pool):
        thread_id = str(uuid4())
        mock_pool.mock_conn.execute = AsyncMock()

        await metrics_repo.update_thread_metrics(thread_id=thread_id)

        expected_sql = """
            INSERT INTO thread_metrics (thread_id, total_messages, ai_messages, manager_messages, escalated, resolution_time, updated_at)
            VALUES ($1, 0, 0, 0, false, NULL, NOW())
            ON CONFLICT (thread_id) DO UPDATE SET
            updated_at = NOW()
        """
        mock_pool.mock_conn.execute.assert_awaited_once_with(
            expected_sql, UUID(thread_id)
        )

    @pytest.mark.asyncio
    async def test_update_thread_metrics_invalid_uuid(self, metrics_repo):
        with pytest.raises(ValueError):
            await metrics_repo.update_thread_metrics(thread_id="invalid-uuid", total_messages=1)

    @pytest.mark.asyncio
    async def test_update_thread_metrics_db_error(self, metrics_repo, mock_pool):
        thread_id = str(uuid4())
        mock_pool.mock_conn.execute = AsyncMock(side_effect=asyncpg.exceptions.ConnectionDoesNotExistError("conn"))
        with pytest.raises(asyncpg.exceptions.ConnectionDoesNotExistError):
            await metrics_repo.update_thread_metrics(thread_id, total_messages=1)

    # --------------------------------------------------------------------------
    # update_project_daily_metrics
    # --------------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_update_project_daily_metrics_insert_new(self, metrics_repo, mock_pool):
        project_id = str(uuid4())
        target_date = date(2025, 1, 1)
        total_threads_delta = 5
        escalations_delta = 2
        tokens_used_delta = 1000
        avg_messages_to_resolution = 3.5

        mock_pool.mock_conn.fetchrow = AsyncMock(return_value=None)  # no existing row
        mock_pool.mock_conn.execute = AsyncMock()

        await metrics_repo.update_project_daily_metrics(
            project_id=project_id,
            date=target_date,
            total_threads_delta=total_threads_delta,
            escalations_delta=escalations_delta,
            tokens_used_delta=tokens_used_delta,
            avg_messages_to_resolution=avg_messages_to_resolution
        )

        assert mock_pool.acquire.call_count == 1
        expected_select_sql = """
                SELECT total_threads, escalations, avg_messages_to_resolution, tokens_used
                FROM project_metrics_daily
                WHERE project_id = $1 AND date = $2
            """
        mock_pool.mock_conn.fetchrow.assert_awaited_once_with(
            expected_select_sql, UUID(project_id), target_date
        )
        expected_insert_sql = """
                    INSERT INTO project_metrics_daily (project_id, date, total_threads, escalations, avg_messages_to_resolution, tokens_used)
                    VALUES ($1, $2, $3, $4, $5, $6)
                """
        mock_pool.mock_conn.execute.assert_awaited_once_with(
            expected_insert_sql, UUID(project_id), target_date,
            total_threads_delta, escalations_delta, avg_messages_to_resolution, tokens_used_delta
        )

    @pytest.mark.asyncio
    async def test_update_project_daily_metrics_update_existing(self, metrics_repo, mock_pool):
        project_id = str(uuid4())
        target_date = date(2025, 1, 1)
        total_threads_delta = 3
        escalations_delta = 1
        tokens_used_delta = 200
        avg_messages_to_resolution = None  # should keep existing

        existing = {
            "total_threads": 10,
            "escalations": 5,
            "avg_messages_to_resolution": 2.5,
            "tokens_used": 500
        }
        mock_pool.mock_conn.fetchrow = AsyncMock(return_value=existing)
        mock_pool.mock_conn.execute = AsyncMock()

        await metrics_repo.update_project_daily_metrics(
            project_id=project_id,
            date=target_date,
            total_threads_delta=total_threads_delta,
            escalations_delta=escalations_delta,
            tokens_used_delta=tokens_used_delta,
            avg_messages_to_resolution=avg_messages_to_resolution
        )

        expected_select_sql = """
                SELECT total_threads, escalations, avg_messages_to_resolution, tokens_used
                FROM project_metrics_daily
                WHERE project_id = $1 AND date = $2
            """
        mock_pool.mock_conn.fetchrow.assert_awaited_once_with(
            expected_select_sql, UUID(project_id), target_date
        )
        expected_update_sql = """
                    UPDATE project_metrics_daily
                    SET total_threads = $1, escalations = $2, avg_messages_to_resolution = $3, tokens_used = $4
                    WHERE project_id = $5 AND date = $6
                """
        mock_pool.mock_conn.execute.assert_awaited_once_with(
            expected_update_sql,
            existing["total_threads"] + total_threads_delta,
            existing["escalations"] + escalations_delta,
            existing["avg_messages_to_resolution"],
            existing["tokens_used"] + tokens_used_delta,
            UUID(project_id),
            target_date
        )

    @pytest.mark.asyncio
    async def test_update_project_daily_metrics_with_avg_override(self, metrics_repo, mock_pool):
        project_id = str(uuid4())
        target_date = date(2025, 1, 1)
        total_threads_delta = 0
        escalations_delta = 0
        tokens_used_delta = 0
        avg_messages_to_resolution = 4.2

        existing = {
            "total_threads": 10,
            "escalations": 5,
            "avg_messages_to_resolution": 2.5,
            "tokens_used": 500
        }
        mock_pool.mock_conn.fetchrow = AsyncMock(return_value=existing)
        mock_pool.mock_conn.execute = AsyncMock()

        await metrics_repo.update_project_daily_metrics(
            project_id=project_id,
            date=target_date,
            total_threads_delta=total_threads_delta,
            escalations_delta=escalations_delta,
            tokens_used_delta=tokens_used_delta,
            avg_messages_to_resolution=avg_messages_to_resolution
        )

        expected_update_sql = """
                    UPDATE project_metrics_daily
                    SET total_threads = $1, escalations = $2, avg_messages_to_resolution = $3, tokens_used = $4
                    WHERE project_id = $5 AND date = $6
                """
        mock_pool.mock_conn.execute.assert_awaited_once_with(
            expected_update_sql,
            existing["total_threads"] + total_threads_delta,
            existing["escalations"] + escalations_delta,
            avg_messages_to_resolution,
            existing["tokens_used"] + tokens_used_delta,
            UUID(project_id),
            target_date
        )

    @pytest.mark.asyncio
    async def test_update_project_daily_metrics_invalid_uuid(self, metrics_repo):
        with pytest.raises(ValueError):
            await metrics_repo.update_project_daily_metrics(
                project_id="invalid",
                date=date.today(),
                total_threads_delta=1
            )

    # --------------------------------------------------------------------------
    # aggregate_for_date
    # --------------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_aggregate_for_date_success(self, metrics_repo, mock_pool):
        target_date = date(2025, 1, 1)
        # Mock threads results
        thread_rows = [
            {"id": uuid4(), "created_at": datetime(2025, 1, 1), "project_id": uuid4()},
            {"id": uuid4(), "created_at": datetime(2025, 1, 1), "project_id": uuid4()},
            {"id": uuid4(), "created_at": datetime(2025, 1, 1), "project_id": uuid4()}
        ]
        # Mock escalations results
        escalation_rows = [
            {"project_id": thread_rows[0]["project_id"], "count": 2},
            {"project_id": thread_rows[1]["project_id"], "count": 1}
        ]
        # Mock fetch, fetchrow, execute in sequence
        mock_pool.mock_conn.fetch = AsyncMock(side_effect=[thread_rows, escalation_rows])
        mock_pool.mock_conn.execute = AsyncMock()

        await metrics_repo.aggregate_for_date(target_date)

        assert mock_pool.acquire.call_count == 1
        # First fetch: threads
        expected_thread_sql = """
                SELECT t.id, t.created_at, c.project_id
                FROM threads t
                JOIN clients c ON t.client_id = c.id
                WHERE t.created_at::date = $1
            """
        mock_pool.mock_conn.fetch.assert_any_call(expected_thread_sql, target_date)
        # Second fetch: escalations
        expected_escalation_sql = """
                SELECT project_id, COUNT(*) as count
                FROM events
                WHERE event_type = 'ticket_created' AND created_at::date = $1
                GROUP BY project_id
            """
        mock_pool.mock_conn.fetch.assert_any_call(expected_escalation_sql, target_date)

        # Check DELETE call
        expected_delete_sql = "DELETE FROM project_metrics_daily WHERE date = $1"
        mock_pool.mock_conn.execute.assert_any_call(expected_delete_sql, target_date)

        # Check INSERT calls
        expected_insert_sql = """
                    INSERT INTO project_metrics_daily (project_id, date, total_threads, escalations, avg_messages_to_resolution, tokens_used)
                    VALUES ($1, $2, $3, $4, NULL, 0)
                """
        # We have three projects: project A (threads=1, escalations=2), B (1,1), C (1,0)
        calls = [
            call(expected_insert_sql, thread_rows[0]["project_id"], target_date, 1, 2),
            call(expected_insert_sql, thread_rows[1]["project_id"], target_date, 1, 1),
            call(expected_insert_sql, thread_rows[2]["project_id"], target_date, 1, 0)
        ]
        mock_pool.mock_conn.execute.assert_has_calls(calls, any_order=True)

    @pytest.mark.asyncio
    async def test_aggregate_for_date_empty_data(self, metrics_repo, mock_pool):
        target_date = date(2025, 1, 1)
        mock_pool.mock_conn.fetch = AsyncMock(side_effect=[[], []])
        mock_pool.mock_conn.execute = AsyncMock()

        await metrics_repo.aggregate_for_date(target_date)

        expected_delete_sql = "DELETE FROM project_metrics_daily WHERE date = $1"
        mock_pool.mock_conn.execute.assert_any_call(expected_delete_sql, target_date)
        # No insert calls
        # There might be no insert calls because all_projects set is empty
        # But the code will iterate over empty set, so no additional execute calls.
        # We can assert that execute was called only once (DELETE)
        assert mock_pool.mock_conn.execute.call_count == 1

    @pytest.mark.asyncio
    async def test_aggregate_for_date_db_error(self, metrics_repo, mock_pool):
        target_date = date(2025, 1, 1)
        mock_pool.mock_conn.fetch = AsyncMock(side_effect=asyncpg.exceptions.UndefinedTableError("no table"))
        with pytest.raises(asyncpg.exceptions.UndefinedTableError):
            await metrics_repo.aggregate_for_date(target_date)

    # --------------------------------------------------------------------------
    # Connection errors for other methods
    # --------------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_connection_error_update_thread(self, metrics_repo, mock_pool):
        mock_pool.acquire.side_effect = asyncpg.exceptions.ConnectionDoesNotExistError("conn closed")
        with pytest.raises(asyncpg.exceptions.ConnectionDoesNotExistError):
            await metrics_repo.update_thread_metrics(str(uuid4()), total_messages=1)

    @pytest.mark.asyncio
    async def test_connection_error_update_project(self, metrics_repo, mock_pool):
        mock_pool.acquire.side_effect = asyncpg.exceptions.ConnectionDoesNotExistError("conn closed")
        with pytest.raises(asyncpg.exceptions.ConnectionDoesNotExistError):
            await metrics_repo.update_project_daily_metrics(str(uuid4()), date.today(), total_threads_delta=1)

    @pytest.mark.asyncio
    async def test_connection_error_aggregate(self, metrics_repo, mock_pool):
        mock_pool.acquire.side_effect = asyncpg.exceptions.ConnectionDoesNotExistError("conn closed")
        with pytest.raises(asyncpg.exceptions.ConnectionDoesNotExistError):
            await metrics_repo.aggregate_for_date(date.today())
