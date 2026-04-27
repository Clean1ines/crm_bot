import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4
import asyncpg

from src.infrastructure.db.repositories.memory_repository import MemoryRepository


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
def memory_repo(mock_pool):
    return MemoryRepository(mock_pool)


class TestMemoryRepository:
    def test_init(self, memory_repo, mock_pool):
        assert memory_repo.pool is mock_pool

    # --------------------------------------------------------------------------
    # get_for_user
    # --------------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_get_for_user_success_without_types(self, memory_repo, mock_pool):
        project_id = str(uuid4())
        client_id = str(uuid4())
        limit = 10
        rows = [
            {
                "id": uuid4(),
                "key": "a",
                "value": 1,
                "type": "preference",
                "created_at": "2021-01-01",
                "updated_at": "2021-01-01",
            },
            {
                "id": uuid4(),
                "key": "b",
                "value": 2,
                "type": "fact",
                "created_at": "2021-01-02",
                "updated_at": "2021-01-02",
            },
        ]
        mock_pool.mock_conn.fetch = AsyncMock(return_value=rows)

        result = await memory_repo.get_for_user_view(project_id, client_id, limit=limit)

        assert mock_pool.acquire.call_count == 1
        expected_sql = """
            SELECT id, key, value, type, created_at, updated_at
            FROM user_memory
            WHERE project_id = $1 AND client_id = $2
        """
        expected_sql += " ORDER BY updated_at DESC LIMIT $" + str(3)
        mock_pool.mock_conn.fetch.assert_awaited_once_with(
            expected_sql, UUID(project_id), UUID(client_id), limit
        )
        assert len(result) == len(rows)
        for i, r in enumerate(result):
            assert r.id == str(rows[i]["id"])
            assert r.key == rows[i]["key"]
            assert r.value == rows[i]["value"]
            assert r.type == rows[i]["type"]

    @pytest.mark.asyncio
    async def test_get_for_user_success_with_types(self, memory_repo, mock_pool):
        project_id = str(uuid4())
        client_id = str(uuid4())
        limit = 5
        types = ["preference", "fact"]
        rows = [
            {
                "id": uuid4(),
                "key": "a",
                "value": 1,
                "type": "preference",
                "created_at": "2021-01-01",
                "updated_at": "2021-01-01",
            }
        ]
        mock_pool.mock_conn.fetch = AsyncMock(return_value=rows)

        result = await memory_repo.get_for_user_view(
            project_id, client_id, limit=limit, types=types
        )

        expected_sql = """
            SELECT id, key, value, type, created_at, updated_at
            FROM user_memory
            WHERE project_id = $1 AND client_id = $2
         AND type IN ($3,$4) ORDER BY updated_at DESC LIMIT $5"""
        mock_pool.mock_conn.fetch.assert_awaited_once_with(
            expected_sql, UUID(project_id), UUID(client_id), types[0], types[1], limit
        )
        assert len(result) == len(rows)

    @pytest.mark.asyncio
    async def test_get_for_user_limit_zero(self, memory_repo, mock_pool):
        mock_pool.mock_conn.fetch = AsyncMock(
            side_effect=asyncpg.exceptions.InvalidParameterValueError("LIMIT 0")
        )
        with pytest.raises(asyncpg.exceptions.InvalidParameterValueError):
            await memory_repo.get_for_user_view(str(uuid4()), str(uuid4()), limit=0)

    @pytest.mark.asyncio
    async def test_get_for_user_empty_result(self, memory_repo, mock_pool):
        mock_pool.mock_conn.fetch = AsyncMock(return_value=[])
        result = await memory_repo.get_for_user_view(str(uuid4()), str(uuid4()))
        assert result == []

    @pytest.mark.asyncio
    async def test_get_for_user_type_error_none_id(self, memory_repo):
        with pytest.raises(TypeError):
            await memory_repo.get_for_user_view(None, str(uuid4()))
        with pytest.raises(TypeError):
            await memory_repo.get_for_user_view(str(uuid4()), None)

    # --------------------------------------------------------------------------
    # set
    # --------------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_set_success_insert(self, memory_repo, mock_pool):
        project_id = str(uuid4())
        client_id = str(uuid4())
        key = "test_key"
        value = {"a": 1}
        type_ = "preference"
        mock_pool.mock_conn.execute = AsyncMock()

        await memory_repo.set(project_id, client_id, key, value, type_)

        expected_sql = """
                INSERT INTO user_memory (project_id, client_id, key, value, type, updated_at)
                VALUES ($1, $2, $3, $4, $5, NOW())
                ON CONFLICT (project_id, client_id, key) DO UPDATE
                SET value = EXCLUDED.value,
                    type = EXCLUDED.type,
                    updated_at = NOW()
            """
        mock_pool.mock_conn.execute.assert_awaited_once_with(
            expected_sql, UUID(project_id), UUID(client_id), key, value, type_
        )
        assert mock_pool.acquire.call_count == 1

    @pytest.mark.asyncio
    async def test_set_success_update(self, memory_repo, mock_pool):
        # same as insert because UPSERT
        project_id = str(uuid4())
        client_id = str(uuid4())
        key = "existing"
        value = "new"
        type_ = "fact"
        mock_pool.mock_conn.execute = AsyncMock()
        await memory_repo.set(project_id, client_id, key, value, type_)
        # No need to verify different; just ensure call made
        assert mock_pool.mock_conn.execute.called

    @pytest.mark.asyncio
    async def test_set_not_null_error(self, memory_repo, mock_pool):
        mock_pool.mock_conn.execute = AsyncMock(
            side_effect=asyncpg.exceptions.NotNullViolationError("null")
        )
        with pytest.raises(asyncpg.exceptions.NotNullViolationError):
            await memory_repo.set(str(uuid4()), str(uuid4()), "key", "value", "type")

    @pytest.mark.asyncio
    async def test_set_foreign_key_error(self, memory_repo, mock_pool):
        mock_pool.mock_conn.execute = AsyncMock(
            side_effect=asyncpg.exceptions.ForeignKeyViolationError("fk")
        )
        with pytest.raises(asyncpg.exceptions.ForeignKeyViolationError):
            await memory_repo.set(str(uuid4()), str(uuid4()), "key", "value", "type")

    @pytest.mark.asyncio
    async def test_set_type_error_none_id(self, memory_repo):
        with pytest.raises(TypeError):
            await memory_repo.set(None, str(uuid4()), "key", "value", "type")
        with pytest.raises(TypeError):
            await memory_repo.set(str(uuid4()), None, "key", "value", "type")

    # --------------------------------------------------------------------------
    # delete
    # --------------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_delete_success(self, memory_repo, mock_pool):
        project_id = str(uuid4())
        client_id = str(uuid4())
        key = "test_key"
        mock_pool.mock_conn.execute = AsyncMock(return_value="DELETE 1")

        result = await memory_repo.delete(project_id, client_id, key)

        expected_sql = """
                DELETE FROM user_memory
                WHERE project_id = $1 AND client_id = $2 AND key = $3
            """
        mock_pool.mock_conn.execute.assert_awaited_once_with(
            expected_sql, UUID(project_id), UUID(client_id), key
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_not_found(self, memory_repo, mock_pool):
        mock_pool.mock_conn.execute = AsyncMock(return_value="DELETE 0")
        result = await memory_repo.delete(str(uuid4()), str(uuid4()), "nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_type_error_none_id(self, memory_repo):
        with pytest.raises(TypeError):
            await memory_repo.delete(None, str(uuid4()), "key")
        with pytest.raises(TypeError):
            await memory_repo.delete(str(uuid4()), None, "key")

    # --------------------------------------------------------------------------
    # clear_for_user
    # --------------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_clear_for_user_success(self, memory_repo, mock_pool):
        project_id = str(uuid4())
        client_id = str(uuid4())
        mock_pool.mock_conn.execute = AsyncMock()

        await memory_repo.clear_for_user(project_id, client_id)

        expected_sql = """
                DELETE FROM user_memory
                WHERE project_id = $1 AND client_id = $2
            """
        mock_pool.mock_conn.execute.assert_awaited_once_with(
            expected_sql, UUID(project_id), UUID(client_id)
        )
        assert mock_pool.acquire.call_count == 1

    @pytest.mark.asyncio
    async def test_clear_for_user_type_error_none_id(self, memory_repo):
        with pytest.raises(TypeError):
            await memory_repo.clear_for_user(None, str(uuid4()))
        with pytest.raises(TypeError):
            await memory_repo.clear_for_user(str(uuid4()), None)

    # --------------------------------------------------------------------------
    # get_lifecycle
    # --------------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_get_lifecycle_success_with_dict_value(self, memory_repo, mock_pool):
        project_id = str(uuid4())
        client_id = str(uuid4())
        row = {"value": {"stage": "warm"}}
        mock_pool.mock_conn.fetchrow = AsyncMock(return_value=row)

        result = await memory_repo.get_lifecycle(project_id, client_id)

        expected_sql = """
                SELECT value
                FROM user_memory
                WHERE project_id = $1 AND client_id = $2 AND type = 'lifecycle' AND key = 'stage'
                ORDER BY updated_at DESC
                LIMIT 1
            """
        mock_pool.mock_conn.fetchrow.assert_awaited_once_with(
            expected_sql, UUID(project_id), UUID(client_id)
        )
        assert result == "warm"

    @pytest.mark.asyncio
    async def test_get_lifecycle_success_with_string_value(
        self, memory_repo, mock_pool
    ):
        # For backward compatibility: value is a string directly
        project_id = str(uuid4())
        client_id = str(uuid4())
        row = {"value": "warm"}
        mock_pool.mock_conn.fetchrow = AsyncMock(return_value=row)

        result = await memory_repo.get_lifecycle(project_id, client_id)

        assert result == "warm"

    @pytest.mark.asyncio
    async def test_get_lifecycle_not_found(self, memory_repo, mock_pool):
        mock_pool.mock_conn.fetchrow = AsyncMock(return_value=None)
        result = await memory_repo.get_lifecycle(str(uuid4()), str(uuid4()))
        assert result is None

    @pytest.mark.asyncio
    async def test_get_lifecycle_invalid_stage(self, memory_repo, mock_pool):
        # value dict but missing stage key
        row = {"value": {"something": "else"}}
        mock_pool.mock_conn.fetchrow = AsyncMock(return_value=row)
        result = await memory_repo.get_lifecycle(str(uuid4()), str(uuid4()))
        assert result is None

    @pytest.mark.asyncio
    async def test_get_lifecycle_type_error_none_id(self, memory_repo):
        with pytest.raises(TypeError):
            await memory_repo.get_lifecycle(None, str(uuid4()))
        with pytest.raises(TypeError):
            await memory_repo.get_lifecycle(str(uuid4()), None)

    # --------------------------------------------------------------------------
    # set_lifecycle
    # --------------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_set_lifecycle_success(self, memory_repo, mock_pool):
        project_id = str(uuid4())
        client_id = str(uuid4())
        lifecycle = "hot"
        # We need to mock the set method's internal execute
        # set_lifecycle calls self.set, which uses the pool.
        # We can mock the set method or allow it to call real set, but then we need to mock the DB call.
        # Simplest: let set_lifecycle call set, and mock set's execute.
        mock_pool.mock_conn.execute = AsyncMock()

        await memory_repo.set_lifecycle(project_id, client_id, lifecycle)

        # Verify that set was called with correct parameters
        # We can check the execute call that set makes.
        expected_sql = """
                INSERT INTO user_memory (project_id, client_id, key, value, type, updated_at)
                VALUES ($1, $2, $3, $4, $5, NOW())
                ON CONFLICT (project_id, client_id, key) DO UPDATE
                SET value = EXCLUDED.value,
                    type = EXCLUDED.type,
                    updated_at = NOW()
            """
        mock_pool.mock_conn.execute.assert_awaited_once_with(
            expected_sql,
            UUID(project_id),
            UUID(client_id),
            "stage",
            {"stage": lifecycle},
            "lifecycle",
        )
        assert mock_pool.acquire.call_count == 1

    @pytest.mark.asyncio
    async def test_set_lifecycle_type_error_none_id(self, memory_repo):
        with pytest.raises(TypeError):
            await memory_repo.set_lifecycle(None, str(uuid4()), "hot")
        with pytest.raises(TypeError):
            await memory_repo.set_lifecycle(str(uuid4()), None, "hot")

    # --------------------------------------------------------------------------
    # update_by_key
    # --------------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_update_by_key_existing_key(self, memory_repo, mock_pool):
        project_id = str(uuid4())
        client_id = str(uuid4())
        key = "existing"
        value = "new value"
        # First SELECT to get type
        row = {"type": "original_type"}
        mock_pool.mock_conn.fetchrow = AsyncMock(return_value=row)
        # Then set will be called, which will execute the UPSERT
        mock_pool.mock_conn.execute = AsyncMock()

        await memory_repo.update_by_key(project_id, client_id, key, value)

        # First acquire for SELECT
        assert mock_pool.acquire.call_count == 2  # one for SELECT, one for set
        expected_select_sql = """
                SELECT type FROM user_memory
                WHERE project_id = $1 AND client_id = $2 AND key = $3
            """
        mock_pool.mock_conn.fetchrow.assert_awaited_once_with(
            expected_select_sql, UUID(project_id), UUID(client_id), key
        )
        # Then set is called with the retrieved type
        expected_set_sql = """
                INSERT INTO user_memory (project_id, client_id, key, value, type, updated_at)
                VALUES ($1, $2, $3, $4, $5, NOW())
                ON CONFLICT (project_id, client_id, key) DO UPDATE
                SET value = EXCLUDED.value,
                    type = EXCLUDED.type,
                    updated_at = NOW()
            """
        mock_pool.mock_conn.execute.assert_awaited_once_with(
            expected_set_sql,
            UUID(project_id),
            UUID(client_id),
            key,
            value,
            "original_type",
        )

    @pytest.mark.asyncio
    async def test_update_by_key_new_key(self, memory_repo, mock_pool):
        project_id = str(uuid4())
        client_id = str(uuid4())
        key = "new"
        value = "value"
        # First SELECT returns None (no row)
        mock_pool.mock_conn.fetchrow = AsyncMock(return_value=None)
        mock_pool.mock_conn.execute = AsyncMock()

        await memory_repo.update_by_key(project_id, client_id, key, value)

        expected_select_sql = """
                SELECT type FROM user_memory
                WHERE project_id = $1 AND client_id = $2 AND key = $3
            """
        mock_pool.mock_conn.fetchrow.assert_awaited_once_with(
            expected_select_sql, UUID(project_id), UUID(client_id), key
        )
        # Then set is called with type 'user_edited'
        expected_set_sql = """
                INSERT INTO user_memory (project_id, client_id, key, value, type, updated_at)
                VALUES ($1, $2, $3, $4, $5, NOW())
                ON CONFLICT (project_id, client_id, key) DO UPDATE
                SET value = EXCLUDED.value,
                    type = EXCLUDED.type,
                    updated_at = NOW()
            """
        mock_pool.mock_conn.execute.assert_awaited_once_with(
            expected_set_sql,
            UUID(project_id),
            UUID(client_id),
            key,
            value,
            "user_edited",
        )

    @pytest.mark.asyncio
    async def test_update_by_key_type_error_none_id(self, memory_repo):
        with pytest.raises(TypeError):
            await memory_repo.update_by_key(None, str(uuid4()), "key", "value")
        with pytest.raises(TypeError):
            await memory_repo.update_by_key(str(uuid4()), None, "key", "value")

    # --------------------------------------------------------------------------
    # Connection errors
    # --------------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_connection_error(self, memory_repo, mock_pool):
        mock_pool.acquire.side_effect = asyncpg.exceptions.ConnectionDoesNotExistError(
            "conn closed"
        )
        with pytest.raises(asyncpg.exceptions.ConnectionDoesNotExistError):
            await memory_repo.get_for_user_view(str(uuid4()), str(uuid4()))

    @pytest.mark.asyncio
    async def test_undefined_table_error(self, memory_repo, mock_pool):
        mock_pool.mock_conn.fetch = AsyncMock(
            side_effect=asyncpg.exceptions.UndefinedTableError("no table")
        )
        with pytest.raises(asyncpg.exceptions.UndefinedTableError):
            await memory_repo.get_for_user_view(str(uuid4()), str(uuid4()))
