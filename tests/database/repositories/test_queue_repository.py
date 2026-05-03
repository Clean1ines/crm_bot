import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
import json
import asyncpg

from src.infrastructure.db.repositories.queue_repository import QueueRepository


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
def queue_repo(mock_pool):
    return QueueRepository(mock_pool)


class TestQueueRepository:
    def test_init(self, queue_repo, mock_pool):
        assert queue_repo.pool is mock_pool

    # ------------------------------------------------------------------
    # enqueue
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_enqueue_success(self, queue_repo, mock_pool):
        task_type = "notify_manager"
        payload = {"thread_id": "123", "message": "Hello"}
        max_attempts = 3
        expected_job_id = uuid4()
        mock_pool.mock_conn.fetchrow = AsyncMock(return_value={"id": expected_job_id})

        result = await queue_repo.enqueue(task_type, payload, max_attempts)

        expected_sql = """
                INSERT INTO public.execution_queue (
                    id, task_type, payload, status, 
                    attempts, max_attempts, next_attempt_at, created_at, updated_at
                )
                VALUES (gen_random_uuid(), $1, $2, 'pending', 0, $3, NULL, NOW(), NOW())
                RETURNING id
            """
        mock_pool.mock_conn.fetchrow.assert_awaited_once_with(
            expected_sql, task_type, json.dumps(payload), max_attempts
        )
        assert result == str(expected_job_id)

    @pytest.mark.asyncio
    async def test_enqueue_without_payload(self, queue_repo, mock_pool):
        task_type = "test"
        expected_job_id = uuid4()
        mock_pool.mock_conn.fetchrow = AsyncMock(return_value={"id": expected_job_id})

        result = await queue_repo.enqueue(task_type, payload=None)

        expected_sql = """
                INSERT INTO public.execution_queue (
                    id, task_type, payload, status, 
                    attempts, max_attempts, next_attempt_at, created_at, updated_at
                )
                VALUES (gen_random_uuid(), $1, $2, 'pending', 0, $3, NULL, NOW(), NOW())
                RETURNING id
            """
        mock_pool.mock_conn.fetchrow.assert_awaited_once_with(
            expected_sql, task_type, None, 3
        )
        assert result == str(expected_job_id)

    @pytest.mark.asyncio
    async def test_enqueue_not_null_error(self, queue_repo, mock_pool):
        mock_pool.mock_conn.fetchrow = AsyncMock(
            side_effect=asyncpg.exceptions.NotNullViolationError("null")
        )
        with pytest.raises(asyncpg.exceptions.NotNullViolationError):
            await queue_repo.enqueue(None, payload={"x": 1})

    # ------------------------------------------------------------------
    # claim_job
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_claim_job_success(self, queue_repo, mock_pool):
        worker_id = "worker-1"
        job_id = uuid4()
        payload = {"key": "value"}
        row = {
            "id": job_id,
            "task_type": "test_task",
            "payload": json.dumps(payload),
            "attempts": 0,
            "max_attempts": 3,
            "created_at": "2026-01-01T00:00:00Z",
        }
        mock_pool.mock_conn.fetchval = AsyncMock(return_value="test_db")
        mock_pool.mock_conn.fetchrow = AsyncMock(return_value=row)

        result = await queue_repo.claim_job(worker_id)

        assert mock_pool.acquire.call_count == 2
        mock_pool.mock_conn.fetchrow.assert_awaited_once()
        sql_arg, worker_id_arg = mock_pool.mock_conn.fetchrow.await_args.args
        assert "UPDATE public.execution_queue" in sql_arg
        assert "status = 'processing'" in sql_arg
        assert "worker_id = $1" in sql_arg
        assert "WHERE status = 'pending'" in sql_arg
        assert "(next_attempt_at IS NULL OR next_attempt_at <= NOW())" in sql_arg
        assert "(attempts < max_attempts OR max_attempts IS NULL)" in sql_arg
        assert "FOR UPDATE SKIP LOCKED" in sql_arg
        assert worker_id_arg == worker_id

        assert result is not None
        assert result.id == str(job_id)
        assert result.task_type == "test_task"
        assert result.payload == payload
        assert result.attempts == 0
        assert result.max_attempts == 3

    @pytest.mark.asyncio
    async def test_claim_job_no_jobs(self, queue_repo, mock_pool):
        worker_id = "worker-1"
        mock_pool.mock_conn.fetchval = AsyncMock(return_value="test_db")
        mock_pool.mock_conn.fetchrow = AsyncMock(return_value=None)

        result = await queue_repo.claim_job(worker_id)

        assert mock_pool.acquire.call_count == 2
        assert result is None

    @pytest.mark.asyncio
    async def test_claim_job_json_decode_error(self, queue_repo, mock_pool):
        worker_id = "worker-1"
        job_id = uuid4()
        row = {
            "id": job_id,
            "task_type": "test",
            "payload": "invalid_json",  # not valid JSON
            "attempts": 0,
            "max_attempts": 3,
            "created_at": "2021-01-01",
        }
        mock_pool.mock_conn.fetchval = AsyncMock(return_value="test_db")
        mock_pool.mock_conn.fetchrow = AsyncMock(return_value=row)

        result = await queue_repo.claim_job(worker_id)

        assert result is not None
        assert result.payload == {}  # error caught, set to empty dict

    # ------------------------------------------------------------------
    # complete_job
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_complete_job_success_done(self, queue_repo, mock_pool):
        job_id = str(uuid4())
        success = True
        error = None
        mock_pool.mock_conn.execute = AsyncMock()

        await queue_repo.complete_job(job_id, success, error)

        mock_pool.mock_conn.execute.assert_awaited_once()
        sql_arg, status_arg, error_arg, job_id_arg = (
            mock_pool.mock_conn.execute.await_args.args
        )
        assert "UPDATE public.execution_queue" in sql_arg
        assert "status = $1" in sql_arg
        assert "error = $2" in sql_arg
        assert "next_attempt_at = NULL" in sql_arg
        assert status_arg == "done"
        assert error_arg is None
        assert job_id_arg == job_id

    @pytest.mark.asyncio
    async def test_complete_job_failed_with_error(self, queue_repo, mock_pool):
        job_id = str(uuid4())
        success = False
        error = "some error"
        mock_pool.mock_conn.execute = AsyncMock()

        await queue_repo.complete_job(job_id, success, error)

        mock_pool.mock_conn.execute.assert_awaited_once()
        sql_arg, status_arg, error_arg, job_id_arg = (
            mock_pool.mock_conn.execute.await_args.args
        )
        assert "UPDATE public.execution_queue" in sql_arg
        assert "status = $1" in sql_arg
        assert "error = $2" in sql_arg
        assert "next_attempt_at = NULL" in sql_arg
        assert status_arg == "failed"
        assert error_arg == error
        assert job_id_arg == job_id

    # ------------------------------------------------------------------
    # release_job
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_release_job_success(self, queue_repo, mock_pool):
        job_id = str(uuid4())
        mock_pool.mock_conn.execute = AsyncMock(return_value="UPDATE 1")

        result = await queue_repo.release_job(job_id, reason="timeout")

        mock_pool.mock_conn.execute.assert_awaited_once()
        sql_arg, job_id_arg = mock_pool.mock_conn.execute.await_args.args
        assert "UPDATE public.execution_queue" in sql_arg
        assert "status = 'pending'" in sql_arg
        assert "locked_at = NULL" in sql_arg
        assert "worker_id = NULL" in sql_arg
        assert "next_attempt_at = NOW()" in sql_arg
        assert "WHERE id = $1 AND status = 'processing'" in sql_arg
        assert job_id_arg == job_id
        assert result is True

    @pytest.mark.asyncio
    async def test_release_job_not_processing(self, queue_repo, mock_pool):
        job_id = str(uuid4())
        mock_pool.mock_conn.execute = AsyncMock(return_value="UPDATE 0")

        result = await queue_repo.release_job(job_id, reason="timeout")

        mock_pool.mock_conn.execute.assert_awaited_once()
        sql_arg, job_id_arg = mock_pool.mock_conn.execute.await_args.args
        assert "UPDATE public.execution_queue" in sql_arg
        assert "status = 'pending'" in sql_arg
        assert "next_attempt_at = NOW()" in sql_arg
        assert "WHERE id = $1 AND status = 'processing'" in sql_arg
        assert job_id_arg == job_id
        assert result is False

    # ------------------------------------------------------------------
    # fail_job
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_fail_job_increment_attempt_success_pending(
        self, queue_repo, mock_pool
    ):
        job_id = str(uuid4())
        error = "transient error"
        increment_attempt = True
        mock_pool.mock_conn.execute = AsyncMock(return_value="UPDATE 1")

        result = await queue_repo.fail_job(
            job_id,
            error,
            increment_attempt,
            retry_delay_seconds=60.0,
        )

        mock_pool.mock_conn.execute.assert_awaited_once()
        sql_arg, error_arg, job_id_arg, retry_delay_arg = (
            mock_pool.mock_conn.execute.await_args.args
        )
        assert "attempts = attempts + 1" in sql_arg
        assert "status = CASE" in sql_arg
        assert "next_attempt_at = CASE" in sql_arg
        assert "NOW() + ($3::double precision * INTERVAL '1 second')" in sql_arg
        assert error_arg == error
        assert job_id_arg == job_id
        assert retry_delay_arg == 60.0
        assert result is True

    @pytest.mark.asyncio
    async def test_fail_job_increment_attempt_max_reached(self, queue_repo, mock_pool):
        job_id = str(uuid4())
        error = "permanent error"
        increment_attempt = True
        mock_pool.mock_conn.execute = AsyncMock(return_value="UPDATE 1")

        result = await queue_repo.fail_job(job_id, error, increment_attempt)

        mock_pool.mock_conn.execute.assert_awaited_once()
        sql_arg, error_arg, job_id_arg, retry_delay_arg = (
            mock_pool.mock_conn.execute.await_args.args
        )
        assert "attempts = attempts + 1" in sql_arg
        assert "WHEN attempts + 1 >= max_attempts THEN 'failed'" in sql_arg
        assert "WHEN attempts + 1 >= max_attempts THEN NOW()" in sql_arg
        assert error_arg == error
        assert job_id_arg == job_id
        assert retry_delay_arg == 0.0
        assert result is True

    @pytest.mark.asyncio
    async def test_fail_job_no_increment(self, queue_repo, mock_pool):
        job_id = str(uuid4())
        error = "failed"
        increment_attempt = False
        mock_pool.mock_conn.execute = AsyncMock(return_value="UPDATE 1")

        result = await queue_repo.fail_job(job_id, error, increment_attempt)

        mock_pool.mock_conn.execute.assert_awaited_once()
        sql_arg, error_arg, job_id_arg = mock_pool.mock_conn.execute.await_args.args
        assert "UPDATE public.execution_queue" in sql_arg
        assert "status = 'failed'" in sql_arg
        assert "next_attempt_at = NULL" in sql_arg
        assert error_arg == error
        assert job_id_arg == job_id
        assert result is True

    @pytest.mark.asyncio
    async def test_fail_job_not_found(self, queue_repo, mock_pool):
        job_id = str(uuid4())
        error = "error"
        mock_pool.mock_conn.execute = AsyncMock(return_value="UPDATE 0")

        result = await queue_repo.fail_job(job_id, error, increment_attempt=True)
        assert result is False

    # ------------------------------------------------------------------
    # increment_attempts
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_increment_attempts_success(self, queue_repo, mock_pool):
        job_id = str(uuid4())
        mock_pool.mock_conn.fetchrow = AsyncMock(
            return_value={"attempts": 2, "max_attempts": 3}
        )

        result = await queue_repo.increment_attempts(job_id)

        expected_sql = """
                UPDATE public.execution_queue
                SET attempts = attempts + 1, updated_at = NOW()
                WHERE id = $1
                RETURNING attempts, max_attempts
            """
        mock_pool.mock_conn.fetchrow.assert_awaited_once_with(expected_sql, job_id)
        assert result == 2

    @pytest.mark.asyncio
    async def test_increment_attempts_not_found(self, queue_repo, mock_pool):
        job_id = str(uuid4())
        mock_pool.mock_conn.fetchrow = AsyncMock(return_value=None)

        result = await queue_repo.increment_attempts(job_id)

        expected_sql = """
                UPDATE public.execution_queue
                SET attempts = attempts + 1, updated_at = NOW()
                WHERE id = $1
                RETURNING attempts, max_attempts
            """
        mock_pool.mock_conn.fetchrow.assert_awaited_once_with(expected_sql, job_id)
        assert result is None

    # ------------------------------------------------------------------
    # get_stale_locked_jobs
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_get_stale_locked_jobs_success(self, queue_repo, mock_pool):
        timeout_minutes = 5
        job_ids = [uuid4(), uuid4()]
        rows = [{"id": job_ids[0]}, {"id": job_ids[1]}]
        mock_pool.mock_conn.fetch = AsyncMock(return_value=rows)

        result = await queue_repo.get_stale_locked_jobs(timeout_minutes)

        mock_pool.mock_conn.fetch.assert_awaited_once()
        sql_arg, timeout_arg = mock_pool.mock_conn.fetch.await_args.args

        assert "SELECT id FROM public.execution_queue" in sql_arg
        assert "WHERE status = 'processing'" in sql_arg
        assert "locked_at < NOW() - ($1::int * INTERVAL '1 minute')" in sql_arg
        assert timeout_arg == timeout_minutes
        assert result == [str(jid) for jid in job_ids]

    @pytest.mark.asyncio
    async def test_get_stale_locked_jobs_empty(self, queue_repo, mock_pool):
        mock_pool.mock_conn.fetch = AsyncMock(return_value=[])
        result = await queue_repo.get_stale_locked_jobs()
        assert result == []

    # ------------------------------------------------------------------
    # Database errors
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_connection_error(self, queue_repo, mock_pool):
        mock_pool.acquire.side_effect = asyncpg.exceptions.ConnectionDoesNotExistError(
            "conn closed"
        )
        with pytest.raises(asyncpg.exceptions.ConnectionDoesNotExistError):
            await queue_repo.enqueue("test")

    @pytest.mark.asyncio
    async def test_undefined_table_error(self, queue_repo, mock_pool):
        mock_pool.mock_conn.fetchrow = AsyncMock(
            side_effect=asyncpg.exceptions.UndefinedTableError("no table")
        )
        with pytest.raises(asyncpg.exceptions.UndefinedTableError):
            await queue_repo.enqueue("test")
