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
                    attempts, max_attempts, created_at, updated_at
                )
                VALUES (gen_random_uuid(), $1, $2, 'pending', 0, $3, NOW(), NOW())
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
                    attempts, max_attempts, created_at, updated_at
                )
                VALUES (gen_random_uuid(), $1, $2, 'pending', 0, $3, NOW(), NOW())
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
        row = {
            "id": job_id,
            "task_type": "test_task",
            "payload": json.dumps({"a": 1}),
            "attempts": 0,
            "max_attempts": 3,
            "created_at": "2021-01-01",
        }
        # First acquire for debug queries
        # Second acquire for main update
        mock_pool.mock_conn.fetchval = AsyncMock(side_effect=["test_db", "public"])
        mock_pool.mock_conn.fetchrow = AsyncMock(return_value=row)

        result = await queue_repo.claim_job(worker_id)

        # Two acquires: first for debug, second for update
        assert mock_pool.acquire.call_count == 2

        # First acquire (debug) fetchval calls
        assert mock_pool.mock_conn.fetchval.call_count == 2
        mock_pool.mock_conn.fetchval.assert_any_call("SELECT current_database()")
        mock_pool.mock_conn.fetchval.assert_any_call("SELECT current_schema()")

        # Second acquire (main)
        expected_sql = """
                UPDATE public.execution_queue
                SET 
                    status = 'processing',
                    updated_at = NOW(),
                    locked_at = NOW(),
                    worker_id = $1
                WHERE id = (
                    SELECT id
                    FROM public.execution_queue
                    WHERE status = 'pending'
                    AND (attempts < max_attempts OR max_attempts IS NULL)
                    ORDER BY created_at ASC
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                )
                RETURNING id, task_type, payload, attempts, max_attempts, created_at
            """
        mock_pool.mock_conn.fetchrow.assert_awaited_once_with(expected_sql, worker_id)

        assert result is not None
        assert result.id == str(job_id)
        assert result.task_type == "test_task"
        assert result.payload == {"a": 1}
        assert result.attempts == 0
        assert result.max_attempts == 3
        assert result.created_at == "2021-01-01"

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

        expected_sql = """
                UPDATE public.execution_queue
                SET 
                    status = $1, 
                    updated_at = NOW(),
                    locked_at = NULL,
                    worker_id = NULL,
                    error = $2
                WHERE id = $3
            """
        mock_pool.mock_conn.execute.assert_awaited_once_with(
            expected_sql, "done", error, job_id
        )

    @pytest.mark.asyncio
    async def test_complete_job_failed_with_error(self, queue_repo, mock_pool):
        job_id = str(uuid4())
        success = False
        error = "some error"
        mock_pool.mock_conn.execute = AsyncMock()

        await queue_repo.complete_job(job_id, success, error)

        expected_sql = """
                UPDATE public.execution_queue
                SET 
                    status = $1, 
                    updated_at = NOW(),
                    locked_at = NULL,
                    worker_id = NULL,
                    error = $2
                WHERE id = $3
            """
        mock_pool.mock_conn.execute.assert_awaited_once_with(
            expected_sql, "failed", error, job_id
        )

    # ------------------------------------------------------------------
    # release_job
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_release_job_success(self, queue_repo, mock_pool):
        job_id = str(uuid4())
        reason = "timeout"
        mock_pool.mock_conn.execute = AsyncMock(return_value="UPDATE 1")

        result = await queue_repo.release_job(job_id, reason)

        expected_sql = """
                UPDATE public.execution_queue
                SET 
                    status = 'pending',
                    updated_at = NOW(),
                    locked_at = NULL,
                    worker_id = NULL
                WHERE id = $1 AND status = 'processing'
            """
        mock_pool.mock_conn.execute.assert_awaited_once_with(expected_sql, job_id)
        assert result is True

    @pytest.mark.asyncio
    async def test_release_job_not_processing(self, queue_repo, mock_pool):
        job_id = str(uuid4())
        mock_pool.mock_conn.execute = AsyncMock(return_value="UPDATE 0")

        result = await queue_repo.release_job(job_id)

        expected_sql = """
                UPDATE public.execution_queue
                SET 
                    status = 'pending',
                    updated_at = NOW(),
                    locked_at = NULL,
                    worker_id = NULL
                WHERE id = $1 AND status = 'processing'
            """
        mock_pool.mock_conn.execute.assert_awaited_once_with(expected_sql, job_id)
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

        result = await queue_repo.fail_job(job_id, error, increment_attempt)

        expected_sql = """
                    UPDATE public.execution_queue
                    SET 
                        attempts = attempts + 1,
                        error = $1,
                        updated_at = NOW(),
                        locked_at = NULL,
                        worker_id = NULL,
                        status = CASE 
                            WHEN attempts + 1 >= max_attempts THEN 'failed'
                            ELSE 'pending'
                        END
                    WHERE id = $2
                """
        mock_pool.mock_conn.execute.assert_awaited_once_with(
            expected_sql, error, job_id
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_fail_job_increment_attempt_max_reached(self, queue_repo, mock_pool):
        job_id = str(uuid4())
        error = "permanent error"
        increment_attempt = True
        mock_pool.mock_conn.execute = AsyncMock(return_value="UPDATE 1")

        result = await queue_repo.fail_job(job_id, error, increment_attempt)

        expected_sql = """
                    UPDATE public.execution_queue
                    SET 
                        attempts = attempts + 1,
                        error = $1,
                        updated_at = NOW(),
                        locked_at = NULL,
                        worker_id = NULL,
                        status = CASE 
                            WHEN attempts + 1 >= max_attempts THEN 'failed'
                            ELSE 'pending'
                        END
                    WHERE id = $2
                """
        mock_pool.mock_conn.execute.assert_awaited_once_with(
            expected_sql, error, job_id
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_fail_job_no_increment(self, queue_repo, mock_pool):
        job_id = str(uuid4())
        error = "failed"
        increment_attempt = False
        mock_pool.mock_conn.execute = AsyncMock(return_value="UPDATE 1")

        result = await queue_repo.fail_job(job_id, error, increment_attempt)

        expected_sql = """
                    UPDATE public.execution_queue
                    SET 
                        error = $1,
                        updated_at = NOW(),
                        locked_at = NULL,
                        worker_id = NULL,
                        status = 'failed'
                    WHERE id = $2
                """
        mock_pool.mock_conn.execute.assert_awaited_once_with(
            expected_sql, error, job_id
        )
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
