import pytest
from unittest.mock import AsyncMock, MagicMock, call
from uuid import uuid4
import asyncpg

from src.infrastructure.db.repositories.user_repository import UserRepository


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
def user_repo(mock_pool):
    return UserRepository(mock_pool)


class TestUserRepository:
    def test_init(self, user_repo, mock_pool):
        assert user_repo.pool is mock_pool

    # ------------------------------------------------------------------
    # get_or_create_by_telegram
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_get_or_create_by_telegram_existing_via_identity(self, user_repo, mock_pool):
        telegram_id = 12345
        first_name = "John"
        username = "johndoe"
        existing_user_id = uuid4()

        # First query: auth_identities returns a row
        mock_pool.mock_conn.fetchrow = AsyncMock(return_value={"user_id": existing_user_id})

        result = await user_repo.get_or_create_by_telegram(telegram_id, first_name, username)

        expected_sql = """
                SELECT user_id
                FROM auth_identities
                WHERE provider = 'telegram' AND provider_id = $1
            """
        mock_pool.mock_conn.fetchrow.assert_awaited_once_with(expected_sql, str(telegram_id))
        assert result == (str(existing_user_id), False)

    @pytest.mark.asyncio
    async def test_get_or_create_by_telegram_existing_legacy(self, user_repo, mock_pool):
        telegram_id = 12345
        first_name = "John"
        username = "johndoe"
        existing_user_id = uuid4()

        # First query: auth_identities returns None
        mock_pool.mock_conn.fetchrow = AsyncMock(side_effect=[None, {"id": existing_user_id}])
        # Second query: legacy users table returns a row
        # Then execute for identity insert
        mock_pool.mock_conn.execute = AsyncMock()

        result = await user_repo.get_or_create_by_telegram(telegram_id, first_name, username)

        # First fetchrow call (identity)
        expected_identity_sql = """
                SELECT user_id
                FROM auth_identities
                WHERE provider = 'telegram' AND provider_id = $1
            """
        mock_pool.mock_conn.fetchrow.assert_any_call(expected_identity_sql, str(telegram_id))
        # Second fetchrow call (legacy users)
        expected_legacy_sql = """
                SELECT id FROM users WHERE telegram_id = $1
            """
        mock_pool.mock_conn.fetchrow.assert_any_call(expected_legacy_sql, telegram_id)
        # Identity insert
        expected_identity_insert = """
                    INSERT INTO auth_identities (user_id, provider, provider_id)
                    VALUES ($1, 'telegram', $2)
                    ON CONFLICT (provider, provider_id) DO NOTHING
                """
        mock_pool.mock_conn.execute.assert_awaited_once_with(expected_identity_insert, str(existing_user_id), str(telegram_id))
        assert result == (str(existing_user_id), False)

    @pytest.mark.asyncio
    async def test_get_or_create_by_telegram_new_user(self, user_repo, mock_pool):
        telegram_id = 12345
        first_name = "John"
        username = "johndoe"
        new_user_id = uuid4()

        # First query: auth_identities returns None
        # Second query: legacy users returns None
        mock_pool.mock_conn.fetchrow = AsyncMock(side_effect=[None, None])
        # Then fetchval for insert returns new user_id
        mock_pool.mock_conn.fetchval = AsyncMock(return_value=new_user_id)
        # Then execute for identity insert
        mock_pool.mock_conn.execute = AsyncMock()

        result = await user_repo.get_or_create_by_telegram(telegram_id, first_name, username)

        expected_insert_user_sql = """
                INSERT INTO users (id, telegram_id, username, full_name)
                VALUES (gen_random_uuid(), $1, $2, $3)
                RETURNING id
            """
        mock_pool.mock_conn.fetchval.assert_awaited_once_with(expected_insert_user_sql, telegram_id, username, first_name)

        # FIXED: adjusted indentation to match actual SQL (16 spaces)
        expected_identity_insert = """
                INSERT INTO auth_identities (user_id, provider, provider_id)
                VALUES ($1, 'telegram', $2)
            """
        mock_pool.mock_conn.execute.assert_awaited_once_with(expected_identity_insert, str(new_user_id), str(telegram_id))
        assert result == (str(new_user_id), True)

    @pytest.mark.asyncio
    async def test_get_or_create_by_telegram_username_none(self, user_repo, mock_pool):
        telegram_id = 12345
        first_name = "John"
        new_user_id = uuid4()

        mock_pool.mock_conn.fetchrow = AsyncMock(side_effect=[None, None])
        mock_pool.mock_conn.fetchval = AsyncMock(return_value=new_user_id)
        mock_pool.mock_conn.execute = AsyncMock()

        result = await user_repo.get_or_create_by_telegram(telegram_id, first_name, username=None)

        expected_insert_user_sql = """
                INSERT INTO users (id, telegram_id, username, full_name)
                VALUES (gen_random_uuid(), $1, $2, $3)
                RETURNING id
            """
        mock_pool.mock_conn.fetchval.assert_awaited_once_with(expected_insert_user_sql, telegram_id, None, first_name)
        assert result == (str(new_user_id), True)

    @pytest.mark.asyncio
    async def test_get_or_create_by_telegram_unique_violation(self, user_repo, mock_pool):
        # Simulate parallel insert causing UniqueViolationError
        telegram_id = 12345
        first_name = "John"

        mock_pool.mock_conn.fetchrow = AsyncMock(side_effect=[None, None])
        mock_pool.mock_conn.fetchval = AsyncMock(side_effect=asyncpg.exceptions.UniqueViolationError("duplicate"))

        with pytest.raises(asyncpg.exceptions.UniqueViolationError):
            await user_repo.get_or_create_by_telegram(telegram_id, first_name)

    # ------------------------------------------------------------------
    # add_identity
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_add_identity_success(self, user_repo, mock_pool):
        user_id = str(uuid4())
        provider = "email"
        provider_id = f"{uuid4().hex}@example.com"
        mock_pool.mock_conn.fetchrow = AsyncMock(return_value=None)
        mock_pool.mock_conn.execute = AsyncMock()

        await user_repo.add_identity(user_id, provider, provider_id)

        expected_sql = """
                INSERT INTO auth_identities (user_id, provider, provider_id)
                VALUES ($1, $2, $3)
            """
        mock_pool.mock_conn.execute.assert_awaited_once_with(expected_sql, user_id, provider, provider_id)

    @pytest.mark.asyncio
    async def test_add_identity_duplicate(self, user_repo, mock_pool):
        user_id = str(uuid4())
        provider = "email"
        provider_id = f"{uuid4().hex}@example.com"
        mock_pool.mock_conn.fetchrow = AsyncMock(return_value={"user_id": user_id})
        mock_pool.mock_conn.execute = AsyncMock()

        # Same provider identity already linked to this user is idempotent.
        await user_repo.add_identity(user_id, provider, provider_id)
        mock_pool.mock_conn.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_add_identity_fk_error(self, user_repo, mock_pool):
        user_id = str(uuid4())
        mock_pool.mock_conn.fetchrow = AsyncMock(return_value=None)
        mock_pool.mock_conn.execute = AsyncMock(side_effect=asyncpg.exceptions.ForeignKeyViolationError("fk"))
        with pytest.raises(asyncpg.exceptions.ForeignKeyViolationError):
            await user_repo.add_identity(user_id, "telegram", str(uuid4().int))

    @pytest.mark.asyncio
    async def test_add_identity_not_null_error(self, user_repo, mock_pool):
        mock_pool.mock_conn.fetchrow = AsyncMock(return_value=None)
        mock_pool.mock_conn.execute = AsyncMock(side_effect=asyncpg.exceptions.NotNullViolationError("null"))
        with pytest.raises(asyncpg.exceptions.NotNullViolationError):
            await user_repo.add_identity(str(uuid4()), None, str(uuid4().int))

    # ------------------------------------------------------------------
    # get_user_by_telegram
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_get_user_by_telegram_success(self, user_repo, mock_pool):
        telegram_id = 12345
        row = {"id": uuid4(), "telegram_id": 12345, "username": "john", "full_name": "John Doe"}
        mock_pool.mock_conn.fetchrow = AsyncMock(return_value=row)

        result = await user_repo.get_user_by_telegram_view(telegram_id)

        expected_sql = """
                SELECT u.*
                FROM users u
                JOIN auth_identities ai ON ai.user_id = u.id
                WHERE ai.provider = 'telegram' AND ai.provider_id = $1
            """
        mock_pool.mock_conn.fetchrow.assert_awaited_once_with(expected_sql, str(telegram_id))
        assert result.id == str(row['id'])
        assert result.username == row.get('username')
        assert result.email == row.get('email')
        assert result.full_name == row.get('full_name')

    @pytest.mark.asyncio
    async def test_get_user_by_telegram_not_found(self, user_repo, mock_pool):
        mock_pool.mock_conn.fetchrow = AsyncMock(return_value=None)
        result = await user_repo.get_user_by_telegram_view(99999)
        assert result is None

    # ------------------------------------------------------------------
    # get_user_by_id
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_get_user_by_id_success(self, user_repo, mock_pool):
        user_id = str(uuid4())
        row = {"id": user_id, "username": "john"}
        mock_pool.mock_conn.fetchrow = AsyncMock(return_value=row)

        result = await user_repo.get_user_by_id_view(user_id)

        expected_sql = "SELECT * FROM users WHERE id = $1"
        mock_pool.mock_conn.fetchrow.assert_awaited_once_with(expected_sql, user_id)
        assert result.id == str(row['id'])
        assert result.username == row.get('username')
        assert result.email == row.get('email')
        assert result.full_name == row.get('full_name')

    @pytest.mark.asyncio
    async def test_get_user_by_id_not_found(self, user_repo, mock_pool):
        mock_pool.mock_conn.fetchrow = AsyncMock(return_value=None)
        result = await user_repo.get_user_by_id_view(str(uuid4()))
        assert result is None

    # ------------------------------------------------------------------
    # get_user_by_email
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_get_user_by_email_success(self, user_repo, mock_pool):
        email = "test@example.com"
        row = {"id": uuid4(), "email": email}
        mock_pool.mock_conn.fetchrow = AsyncMock(return_value=row)

        result = await user_repo.get_user_by_email_view(email)

        expected_sql = "SELECT * FROM users WHERE email = $1"
        mock_pool.mock_conn.fetchrow.assert_awaited_once_with(expected_sql, email)
        assert result.id == str(row['id'])
        assert result.username == row.get('username')
        assert result.email == row.get('email')
        assert result.full_name == row.get('full_name')

    @pytest.mark.asyncio
    async def test_get_user_by_email_not_found(self, user_repo, mock_pool):
        mock_pool.mock_conn.fetchrow = AsyncMock(return_value=None)
        result = await user_repo.get_user_by_email_view("nonexistent@example.com")
        assert result is None

    # ------------------------------------------------------------------
    # update_user
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_update_user_success(self, user_repo, mock_pool):
        user_id = str(uuid4())
        data = {"full_name": "Jane Doe", "email": "jane@example.com"}
        mock_pool.mock_conn.execute = AsyncMock(return_value="UPDATE 1")

        result = await user_repo.update_user(user_id, data)

        expected_sql = """
            UPDATE users
            SET full_name = $2, email = $3, updated_at = NOW()
            WHERE id = $1
        """
        mock_pool.mock_conn.execute.assert_awaited_once_with(
            expected_sql, user_id, "Jane Doe", "jane@example.com"
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_update_user_empty_data(self, user_repo, mock_pool):
        result = await user_repo.update_user(str(uuid4()), {})
        assert result is True
        mock_pool.mock_conn.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_user_not_found(self, user_repo, mock_pool):
        user_id = str(uuid4())
        data = {"full_name": "New Name"}
        mock_pool.mock_conn.execute = AsyncMock(return_value="UPDATE 0")

        result = await user_repo.update_user(user_id, data)

        expected_sql = """
            UPDATE users
            SET full_name = $2, updated_at = NOW()
            WHERE id = $1
        """
        mock_pool.mock_conn.execute.assert_awaited_once_with(expected_sql, user_id, "New Name")
        assert result is False

    @pytest.mark.asyncio
    async def test_update_user_undefined_column_error(self, user_repo, mock_pool):
        user_id = str(uuid4())
        data = {"nonexistent_column": "value"}
        mock_pool.mock_conn.execute = AsyncMock(side_effect=asyncpg.exceptions.UndefinedColumnError("column not found"))

        with pytest.raises(asyncpg.exceptions.UndefinedColumnError):
            await user_repo.update_user(user_id, data)

    # ------------------------------------------------------------------
    # Database errors
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_connection_error(self, user_repo, mock_pool):
        mock_pool.acquire.side_effect = asyncpg.exceptions.ConnectionDoesNotExistError("conn closed")
        with pytest.raises(asyncpg.exceptions.ConnectionDoesNotExistError):
            await user_repo.get_user_by_id_view(str(uuid4()))

    @pytest.mark.asyncio
    async def test_undefined_table_error(self, user_repo, mock_pool):
        mock_pool.mock_conn.fetchrow = AsyncMock(side_effect=asyncpg.exceptions.UndefinedTableError("no table"))
        with pytest.raises(asyncpg.exceptions.UndefinedTableError):
            await user_repo.get_user_by_id_view(str(uuid4()))
