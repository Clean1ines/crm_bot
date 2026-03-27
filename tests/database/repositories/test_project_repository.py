import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call, ANY
from uuid import UUID, uuid4
from datetime import datetime
import asyncpg

from src.database.repositories.project_repository import ProjectRepository
from src.utils.encryption import encrypt_token, decrypt_token


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
def project_repo(mock_pool):
    return ProjectRepository(mock_pool)


class TestProjectRepository:
    def test_init(self, project_repo, mock_pool):
        assert project_repo.pool is mock_pool

    # ------------------------------------------------------------------
    # get_project_settings
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_get_project_settings_success(self, project_repo, mock_pool):
        project_id = str(uuid4())
        row = {
            "system_prompt": "prompt",
            "bot_token": "encrypted_token",
            "webhook_url": "https://example.com",
            "manager_bot_token": "encrypted_manager_token",
            "webhook_secret": "secret",
            "template_slug": "support",
            "is_pro_mode": True,
            "client_bot_username": "client_bot",
            "manager_bot_username": "manager_bot",
        }
        manager_rows = [{"manager_chat_id": "123"}, {"manager_chat_id": "456"}]
        mock_pool.mock_conn.fetchrow = AsyncMock(return_value=row)
        mock_pool.mock_conn.fetch = AsyncMock(return_value=manager_rows)

        with patch("src.database.repositories.project_repository.decrypt_token") as mock_decrypt:
            mock_decrypt.side_effect = lambda x: f"decrypted_{x}" if x else None
            result = await project_repo.get_project_settings(project_id)

        # FIXED: Only one acquire because both queries reuse the same connection
        assert mock_pool.acquire.call_count == 1
        expected_sql = """
                SELECT system_prompt, bot_token, webhook_url, manager_bot_token, 
                       webhook_secret, template_slug, is_pro_mode,
                       client_bot_username, manager_bot_username
                FROM projects
                WHERE id = $1
            """
        mock_pool.mock_conn.fetchrow.assert_awaited_once_with(expected_sql, UUID(project_id))

        expected_managers_sql = """
                SELECT manager_chat_id FROM project_managers
                WHERE project_id = $1
            """
        mock_pool.mock_conn.fetch.assert_awaited_once_with(expected_managers_sql, UUID(project_id))

        assert result["system_prompt"] == "prompt"
        assert result["bot_token"] == "decrypted_encrypted_token"
        assert result["manager_bot_token"] == "decrypted_encrypted_manager_token"
        assert result["webhook_secret"] == "secret"
        assert result["template_slug"] == "support"
        assert result["is_pro_mode"] is True
        assert result["client_bot_username"] == "client_bot"
        assert result["manager_bot_username"] == "manager_bot"
        assert result["manager_chat_ids"] == ["123", "456"]

    @pytest.mark.asyncio
    async def test_get_project_settings_not_found(self, project_repo, mock_pool):
        mock_pool.mock_conn.fetchrow = AsyncMock(return_value=None)
        result = await project_repo.get_project_settings(str(uuid4()))
        assert result == {}

    @pytest.mark.asyncio
    async def test_get_project_settings_no_managers(self, project_repo, mock_pool):
        row = {
            "system_prompt": "prompt",
            "bot_token": None,
            "webhook_url": None,
            "manager_bot_token": None,
            "webhook_secret": None,
            "template_slug": None,
            "is_pro_mode": False,
            "client_bot_username": None,
            "manager_bot_username": None,
        }
        mock_pool.mock_conn.fetchrow = AsyncMock(return_value=row)
        mock_pool.mock_conn.fetch = AsyncMock(return_value=[])  # no managers
        with patch("src.database.repositories.project_repository.decrypt_token", return_value=None):
            result = await project_repo.get_project_settings(str(uuid4()))
        assert result["manager_chat_ids"] == []

    # ------------------------------------------------------------------
    # get_bot_token
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_get_bot_token_success(self, project_repo, mock_pool):
        project_id = str(uuid4())
        encrypted = "encrypted_token"
        mock_pool.mock_conn.fetchval = AsyncMock(return_value=encrypted)
        with patch("src.database.repositories.project_repository.decrypt_token", return_value="decrypted_token"):
            token = await project_repo.get_bot_token(project_id)
        assert token == "decrypted_token"
        expected_sql = """
                SELECT bot_token FROM projects WHERE id = $1
            """
        mock_pool.mock_conn.fetchval.assert_awaited_once_with(expected_sql, UUID(project_id))

    @pytest.mark.asyncio
    async def test_get_bot_token_none(self, project_repo, mock_pool):
        mock_pool.mock_conn.fetchval = AsyncMock(return_value=None)
        token = await project_repo.get_bot_token(str(uuid4()))
        assert token is None

    # ------------------------------------------------------------------
    # set_bot_token
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_set_bot_token_with_token(self, project_repo, mock_pool):
        project_id = str(uuid4())
        token = "real_token"
        mock_pool.mock_conn.execute = AsyncMock()
        with patch("src.database.repositories.project_repository.encrypt_token", return_value="encrypted_token") as mock_encrypt:
            with patch.object(project_repo, "_get_bot_username", AsyncMock(return_value="bot_username")):
                await project_repo.set_bot_token(project_id, token)

        mock_encrypt.assert_called_once_with(token)
        expected_sql = """
                UPDATE projects 
                SET bot_token = $1, client_bot_username = $2, updated_at = NOW()
                WHERE id = $3
            """
        mock_pool.mock_conn.execute.assert_awaited_once_with(
            expected_sql, "encrypted_token", "bot_username", UUID(project_id)
        )

    @pytest.mark.asyncio
    async def test_set_bot_token_with_token_username_fetch_fails(self, project_repo, mock_pool):
        project_id = str(uuid4())
        token = "real_token"
        mock_pool.mock_conn.execute = AsyncMock()
        with patch("src.database.repositories.project_repository.encrypt_token", return_value="encrypted_token"):
            with patch.object(project_repo, "_get_bot_username", AsyncMock(return_value=None)):
                await project_repo.set_bot_token(project_id, token)

        expected_sql = """
                UPDATE projects 
                SET bot_token = $1, client_bot_username = $2, updated_at = NOW()
                WHERE id = $3
            """
        mock_pool.mock_conn.execute.assert_awaited_once_with(
            expected_sql, "encrypted_token", None, UUID(project_id)
        )

    @pytest.mark.asyncio
    async def test_set_bot_token_with_none(self, project_repo, mock_pool):
        project_id = str(uuid4())
        mock_pool.mock_conn.execute = AsyncMock()
        with patch("src.database.repositories.project_repository.encrypt_token", return_value=None):
            await project_repo.set_bot_token(project_id, None)
        expected_sql = """
                UPDATE projects 
                SET bot_token = $1, client_bot_username = $2, updated_at = NOW()
                WHERE id = $3
            """
        mock_pool.mock_conn.execute.assert_awaited_once_with(
            expected_sql, None, None, UUID(project_id)
        )

    # ------------------------------------------------------------------
    # get_manager_bot_token
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_get_manager_bot_token_success(self, project_repo, mock_pool):
        project_id = str(uuid4())
        mock_pool.mock_conn.fetchval = AsyncMock(return_value="encrypted")
        with patch("src.database.repositories.project_repository.decrypt_token", return_value="decrypted"):
            token = await project_repo.get_manager_bot_token(project_id)
        assert token == "decrypted"
        expected_sql = """
                SELECT manager_bot_token FROM projects WHERE id = $1
            """
        mock_pool.mock_conn.fetchval.assert_awaited_once_with(expected_sql, UUID(project_id))

    @pytest.mark.asyncio
    async def test_get_manager_bot_token_none(self, project_repo, mock_pool):
        mock_pool.mock_conn.fetchval = AsyncMock(return_value=None)
        token = await project_repo.get_manager_bot_token(str(uuid4()))
        assert token is None

    # ------------------------------------------------------------------
    # set_manager_bot_token
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_set_manager_bot_token_with_token(self, project_repo, mock_pool):
        project_id = str(uuid4())
        token = "real_token"
        mock_pool.mock_conn.execute = AsyncMock()
        with patch("src.database.repositories.project_repository.encrypt_token", return_value="encrypted_token") as mock_encrypt:
            with patch.object(project_repo, "_get_bot_username", AsyncMock(return_value="manager_username")):
                await project_repo.set_manager_bot_token(project_id, token)

        mock_encrypt.assert_called_once_with(token)
        expected_sql = """
                UPDATE projects 
                SET manager_bot_token = $1, manager_bot_username = $2, updated_at = NOW()
                WHERE id = $3
            """
        mock_pool.mock_conn.execute.assert_awaited_once_with(
            expected_sql, "encrypted_token", "manager_username", UUID(project_id)
        )

    @pytest.mark.asyncio
    async def test_set_manager_bot_token_with_none(self, project_repo, mock_pool):
        project_id = str(uuid4())
        mock_pool.mock_conn.execute = AsyncMock()
        with patch("src.database.repositories.project_repository.encrypt_token", return_value=None):
            await project_repo.set_manager_bot_token(project_id, None)
        expected_sql = """
                UPDATE projects 
                SET manager_bot_token = $1, manager_bot_username = $2, updated_at = NOW()
                WHERE id = $3
            """
        mock_pool.mock_conn.execute.assert_awaited_once_with(
            expected_sql, None, None, UUID(project_id)
        )

    # ------------------------------------------------------------------
    # get_webhook_secret / set_webhook_secret
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_get_webhook_secret(self, project_repo, mock_pool):
        project_id = str(uuid4())
        mock_pool.mock_conn.fetchval = AsyncMock(return_value="secret")
        secret = await project_repo.get_webhook_secret(project_id)
        assert secret == "secret"
        expected_sql = """
                SELECT webhook_secret FROM projects WHERE id = $1
            """
        mock_pool.mock_conn.fetchval.assert_awaited_once_with(expected_sql, UUID(project_id))

    @pytest.mark.asyncio
    async def test_set_webhook_secret(self, project_repo, mock_pool):
        project_id = str(uuid4())
        secret = "new_secret"
        mock_pool.mock_conn.execute = AsyncMock()
        await project_repo.set_webhook_secret(project_id, secret)
        expected_sql = """
                UPDATE projects SET webhook_secret = $1, updated_at = NOW()
                WHERE id = $2
            """
        mock_pool.mock_conn.execute.assert_awaited_once_with(
            expected_sql, secret, UUID(project_id)
        )

    # ------------------------------------------------------------------
    # get_managers
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_get_managers(self, project_repo, mock_pool):
        project_id = str(uuid4())
        rows = [{"manager_chat_id": "111"}, {"manager_chat_id": "222"}]
        mock_pool.mock_conn.fetch = AsyncMock(return_value=rows)
        result = await project_repo.get_managers(project_id)
        assert result == ["111", "222"]
        expected_sql = """
                SELECT manager_chat_id FROM project_managers
                WHERE project_id = $1
            """
        mock_pool.mock_conn.fetch.assert_awaited_once_with(expected_sql, UUID(project_id))

    # ------------------------------------------------------------------
    # add_manager
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_add_manager_success(self, project_repo, mock_pool):
        project_id = str(uuid4())
        manager_chat_id = "123"
        mock_pool.mock_conn.execute = AsyncMock()
        await project_repo.add_manager(project_id, manager_chat_id)
        expected_sql = """
                    INSERT INTO project_managers (project_id, manager_chat_id)
                    VALUES ($1, $2)
                """
        mock_pool.mock_conn.execute.assert_awaited_once_with(
            expected_sql, UUID(project_id), manager_chat_id
        )

    @pytest.mark.asyncio
    async def test_add_manager_duplicate(self, project_repo, mock_pool):
        project_id = str(uuid4())
        manager_chat_id = "123"
        mock_pool.mock_conn.execute = AsyncMock(side_effect=asyncpg.exceptions.UniqueViolationError("duplicate"))
        # Should not raise; just log warning
        await project_repo.add_manager(project_id, manager_chat_id)
        mock_pool.mock_conn.execute.assert_awaited_once()

    # ------------------------------------------------------------------
    # remove_manager
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_remove_manager(self, project_repo, mock_pool):
        project_id = str(uuid4())
        manager_chat_id = "123"
        mock_pool.mock_conn.execute = AsyncMock()
        await project_repo.remove_manager(project_id, manager_chat_id)
        expected_sql = """
                DELETE FROM project_managers
                WHERE project_id = $1 AND manager_chat_id = $2
            """
        mock_pool.mock_conn.execute.assert_awaited_once_with(
            expected_sql, UUID(project_id), manager_chat_id
        )

    # ------------------------------------------------------------------
    # apply_template
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_apply_template_success(self, project_repo, mock_pool):
        project_id = str(uuid4())
        template_slug = "support"
        mock_pool.mock_conn.fetchval = AsyncMock(return_value=1)  # template exists
        mock_pool.mock_conn.execute = AsyncMock()
        result = await project_repo.apply_template(project_id, template_slug)
        assert result is True
        expected_check_sql = "SELECT 1 FROM workflow_templates WHERE slug = $1 AND is_active = true"
        mock_pool.mock_conn.fetchval.assert_awaited_once_with(expected_check_sql, template_slug)
        expected_update_sql = """
                UPDATE projects 
                SET template_slug = $1, updated_at = NOW()
                WHERE id = $2
            """
        mock_pool.mock_conn.execute.assert_awaited_once_with(
            expected_update_sql, template_slug, UUID(project_id)
        )

    @pytest.mark.asyncio
    async def test_apply_template_not_found(self, project_repo, mock_pool):
        project_id = str(uuid4())
        template_slug = "nonexistent"
        mock_pool.mock_conn.fetchval = AsyncMock(return_value=None)
        mock_pool.mock_conn.execute = AsyncMock()
        result = await project_repo.apply_template(project_id, template_slug)
        assert result is False
        mock_pool.mock_conn.execute.assert_not_called()

    # ------------------------------------------------------------------
    # set_pro_mode, get_template_slug, get_is_pro_mode
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_set_pro_mode(self, project_repo, mock_pool):
        project_id = str(uuid4())
        mock_pool.mock_conn.execute = AsyncMock()
        await project_repo.set_pro_mode(project_id, True)
        expected_sql = """
                UPDATE projects 
                SET is_pro_mode = $1, updated_at = NOW()
                WHERE id = $2
            """
        mock_pool.mock_conn.execute.assert_awaited_once_with(
            expected_sql, True, UUID(project_id)
        )

    @pytest.mark.asyncio
    async def test_get_template_slug(self, project_repo, mock_pool):
        project_id = str(uuid4())
        mock_pool.mock_conn.fetchval = AsyncMock(return_value="leads")
        slug = await project_repo.get_template_slug(project_id)
        assert slug == "leads"
        expected_sql = "SELECT template_slug FROM projects WHERE id = $1"
        mock_pool.mock_conn.fetchval.assert_awaited_once_with(expected_sql, UUID(project_id))

    @pytest.mark.asyncio
    async def test_get_is_pro_mode(self, project_repo, mock_pool):
        project_id = str(uuid4())
        mock_pool.mock_conn.fetchval = AsyncMock(return_value=True)
        result = await project_repo.get_is_pro_mode(project_id)
        assert result is True
        expected_sql = "SELECT is_pro_mode FROM projects WHERE id = $1"
        mock_pool.mock_conn.fetchval.assert_awaited_once_with(expected_sql, UUID(project_id))

    # ------------------------------------------------------------------
    # find_project_by_manager_token
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_find_project_by_manager_token_found(self, project_repo, mock_pool):
        rows = [
            {"id": uuid4(), "manager_bot_token": "enc1"},
            {"id": uuid4(), "manager_bot_token": "enc2"},
        ]
        mock_pool.mock_conn.fetch = AsyncMock(return_value=rows)
        with patch("src.database.repositories.project_repository.decrypt_token") as mock_decrypt:
            mock_decrypt.side_effect = lambda x: f"decrypted_{x}" if x else None
            result = await project_repo.find_project_by_manager_token("decrypted_enc2")
        assert result == str(rows[1]["id"])
        expected_sql = "SELECT id, manager_bot_token FROM projects WHERE manager_bot_token IS NOT NULL"
        mock_pool.mock_conn.fetch.assert_awaited_once_with(expected_sql)

    @pytest.mark.asyncio
    async def test_find_project_by_manager_token_not_found(self, project_repo, mock_pool):
        rows = [
            {"id": uuid4(), "manager_bot_token": "enc1"},
            {"id": uuid4(), "manager_bot_token": "enc2"},
        ]
        mock_pool.mock_conn.fetch = AsyncMock(return_value=rows)
        with patch("src.database.repositories.project_repository.decrypt_token", return_value="different"):
            result = await project_repo.find_project_by_manager_token("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_find_project_by_manager_token_empty(self, project_repo, mock_pool):
        mock_pool.mock_conn.fetch = AsyncMock(return_value=[])
        result = await project_repo.find_project_by_manager_token("token")
        assert result is None

    # ------------------------------------------------------------------
    # manager webhook secret
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_get_manager_webhook_secret(self, project_repo, mock_pool):
        project_id = str(uuid4())
        mock_pool.mock_conn.fetchval = AsyncMock(return_value="secret")
        secret = await project_repo.get_manager_webhook_secret(project_id)
        assert secret == "secret"
        expected_sql = """
                SELECT manager_webhook_secret FROM projects WHERE id = $1
            """
        mock_pool.mock_conn.fetchval.assert_awaited_once_with(expected_sql, UUID(project_id))

    @pytest.mark.asyncio
    async def test_set_manager_webhook_secret(self, project_repo, mock_pool):
        project_id = str(uuid4())
        secret = "new_secret"
        mock_pool.mock_conn.execute = AsyncMock()
        await project_repo.set_manager_webhook_secret(project_id, secret)
        expected_sql = """
                UPDATE projects SET manager_webhook_secret = $1, updated_at = NOW()
                WHERE id = $2
            """
        mock_pool.mock_conn.execute.assert_awaited_once_with(
            expected_sql, secret, UUID(project_id)
        )

    @pytest.mark.asyncio
    async def test_find_project_by_manager_webhook_secret_found(self, project_repo, mock_pool):
        secret = "mysecret"
        row = {"id": uuid4()}
        mock_pool.mock_conn.fetchrow = AsyncMock(return_value=row)
        result = await project_repo.find_project_by_manager_webhook_secret(secret)
        assert result == str(row["id"])
        expected_sql = """
                SELECT id FROM projects WHERE manager_webhook_secret = $1
            """
        mock_pool.mock_conn.fetchrow.assert_awaited_once_with(expected_sql, secret)

    @pytest.mark.asyncio
    async def test_find_project_by_manager_webhook_secret_not_found(self, project_repo, mock_pool):
        mock_pool.mock_conn.fetchrow = AsyncMock(return_value=None)
        result = await project_repo.find_project_by_manager_webhook_secret("secret")
        assert result is None

    # ------------------------------------------------------------------
    # project_exists
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_project_exists_true(self, project_repo, mock_pool):
        project_id = str(uuid4())
        mock_pool.mock_conn.fetchval = AsyncMock(return_value=1)
        exists = await project_repo.project_exists(project_id)
        assert exists is True
        expected_sql = "SELECT 1 FROM projects WHERE id = $1"
        mock_pool.mock_conn.fetchval.assert_awaited_once_with(expected_sql, UUID(project_id))

    @pytest.mark.asyncio
    async def test_project_exists_false(self, project_repo, mock_pool):
        mock_pool.mock_conn.fetchval = AsyncMock(return_value=None)
        exists = await project_repo.project_exists(str(uuid4()))
        assert exists is False

    # ------------------------------------------------------------------
    # create_project
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_create_project(self, project_repo, mock_pool):
        owner_id = "user123"
        name = "Test Project"
        project_id = uuid4()
        mock_pool.mock_conn.fetchval = AsyncMock(return_value=project_id)
        result = await project_repo.create_project(owner_id, name)
        assert result == str(project_id)
        expected_sql = """
                INSERT INTO projects (id, name, owner_id, bot_token, system_prompt)
                VALUES (gen_random_uuid(), $1, $2, '', 'Ты — полезный AI-ассистент.')
                RETURNING id
            """
        mock_pool.mock_conn.fetchval.assert_awaited_once_with(expected_sql, name, owner_id)

    @pytest.mark.asyncio
    async def test_create_project_with_user_id(self, project_repo, mock_pool):
        user_id = str(uuid4())
        name = "Test Project"
        project_id = uuid4()
        mock_pool.mock_conn.fetchval = AsyncMock(return_value=project_id)
        result = await project_repo.create_project_with_user_id(user_id, name)
        assert result == str(project_id)
        expected_sql = """
                INSERT INTO projects (id, name, owner_id, user_id, bot_token, system_prompt)
                VALUES (gen_random_uuid(), $1, $2, $2, '', 'Ты — полезный AI-ассистент.')
                RETURNING id
            """
        mock_pool.mock_conn.fetchval.assert_awaited_once_with(expected_sql, name, user_id)

    # ------------------------------------------------------------------
    # get_all_projects
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_get_all_projects(self, project_repo, mock_pool):
        rows = [
            {"id": uuid4(), "owner_id": "o1", "user_id": uuid4(), "name": "p1", "is_pro_mode": False, "template_slug": None, "created_at": datetime.now(), "updated_at": datetime.now()},
            {"id": uuid4(), "owner_id": "o2", "user_id": None, "name": "p2", "is_pro_mode": True, "template_slug": "support", "created_at": datetime.now(), "updated_at": datetime.now()}
        ]
        mock_pool.mock_conn.fetch = AsyncMock(return_value=rows)
        result = await project_repo.get_all_projects()
        assert len(result) == len(rows)
        for i, proj in enumerate(result):
            assert proj["id"] == str(rows[i]["id"])
            if rows[i]["owner_id"]:
                assert proj["owner_id"] == str(rows[i]["owner_id"])
            else:
                assert proj.get("owner_id") is None
            if rows[i]["user_id"]:
                assert proj["user_id"] == str(rows[i]["user_id"])
            else:
                assert proj.get("user_id") is None
        expected_sql = """
                SELECT id, owner_id, user_id, name, is_pro_mode, template_slug, created_at, updated_at
                FROM projects
                ORDER BY created_at DESC
            """
        mock_pool.mock_conn.fetch.assert_awaited_once_with(expected_sql)

    # ------------------------------------------------------------------
    # get_project_by_id
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_get_project_by_id_found(self, project_repo, mock_pool):
        project_id = str(uuid4())
        row = {
            "id": project_id,
            "owner_id": "owner",
            "user_id": str(uuid4()),
            "name": "Test",
            "is_pro_mode": True,
            "template_slug": "support",
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
            "client_bot_username": "client_bot",
            "manager_bot_username": "manager_bot"
        }
        mock_pool.mock_conn.fetchrow = AsyncMock(return_value=row)
        result = await project_repo.get_project_by_id(project_id)
        assert result is not None
        assert result["id"] == project_id
        assert result["owner_id"] == "owner"
        assert result["user_id"] == row["user_id"]
        assert result["name"] == "Test"
        assert result["is_pro_mode"] is True
        assert result["template_slug"] == "support"
        assert result["client_bot_username"] == "client_bot"
        assert result["manager_bot_username"] == "manager_bot"
        expected_sql = """
                SELECT id, owner_id, user_id, name, is_pro_mode, template_slug, created_at, updated_at,
                       client_bot_username, manager_bot_username
                FROM projects
                WHERE id = $1
            """
        mock_pool.mock_conn.fetchrow.assert_awaited_once_with(expected_sql, UUID(project_id))

    @pytest.mark.asyncio
    async def test_get_project_by_id_not_found(self, project_repo, mock_pool):
        mock_pool.mock_conn.fetchrow = AsyncMock(return_value=None)
        result = await project_repo.get_project_by_id(str(uuid4()))
        assert result is None

    # ------------------------------------------------------------------
    # update_project
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_update_project(self, project_repo, mock_pool):
        project_id = str(uuid4())
        name = "New Name"
        mock_pool.mock_conn.execute = AsyncMock()
        await project_repo.update_project(project_id, name)
        expected_sql = """
                UPDATE projects SET name = $1, updated_at = NOW()
                WHERE id = $2
            """
        mock_pool.mock_conn.execute.assert_awaited_once_with(expected_sql, name, UUID(project_id))

    @pytest.mark.asyncio
    async def test_update_project_none_name(self, project_repo, mock_pool):
        await project_repo.update_project(str(uuid4()), None)
        mock_pool.mock_conn.execute.assert_not_called()

    # ------------------------------------------------------------------
    # delete_project
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_delete_project(self, project_repo, mock_pool):
        project_id = str(uuid4())
        mock_pool.mock_conn.execute = AsyncMock()
        await project_repo.delete_project(project_id)
        expected_sql = "DELETE FROM projects WHERE id = $1"
        mock_pool.mock_conn.execute.assert_awaited_once_with(expected_sql, UUID(project_id))

    # ------------------------------------------------------------------
    # get_projects_by_owner / get_projects_by_user_id
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_get_projects_by_owner(self, project_repo, mock_pool):
        owner_id = "owner123"
        rows = [
            {"id": uuid4(), "name": "p1", "is_pro_mode": False, "template_slug": None, "created_at": datetime.now(), "updated_at": datetime.now(),
             "client_bot_username": None, "manager_bot_username": None}
        ]
        mock_pool.mock_conn.fetch = AsyncMock(return_value=rows)
        result = await project_repo.get_projects_by_owner(owner_id)
        assert len(result) == len(rows)
        assert result[0]["id"] == str(rows[0]["id"])
        expected_sql = """
                SELECT id, name, is_pro_mode, template_slug, created_at, updated_at,
                       client_bot_username, manager_bot_username
                FROM projects
                WHERE owner_id = $1
                ORDER BY created_at DESC
            """
        mock_pool.mock_conn.fetch.assert_awaited_once_with(expected_sql, owner_id)

    @pytest.mark.asyncio
    async def test_get_projects_by_user_id(self, project_repo, mock_pool):
        user_id = str(uuid4())
        rows = [
            {"id": uuid4(), "name": "p1", "is_pro_mode": False, "template_slug": None, "created_at": datetime.now(), "updated_at": datetime.now(),
             "client_bot_username": None, "manager_bot_username": None}
        ]
        mock_pool.mock_conn.fetch = AsyncMock(return_value=rows)
        result = await project_repo.get_projects_by_user_id(user_id)
        assert len(result) == len(rows)
        assert result[0]["id"] == str(rows[0]["id"])
        assert result[0]["user_id"] == user_id
        expected_sql = """
                SELECT id, name, is_pro_mode, template_slug, created_at, updated_at,
                       client_bot_username, manager_bot_username
                FROM projects
                WHERE user_id = $1
                ORDER BY created_at DESC
            """
        mock_pool.mock_conn.fetch.assert_awaited_once_with(expected_sql, user_id)

    # ------------------------------------------------------------------
    # Invalid UUID errors
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_invalid_uuid_in_get_project_settings(self, project_repo):
        with pytest.raises(ValueError):
            await project_repo.get_project_settings("invalid-uuid")

    @pytest.mark.asyncio
    async def test_invalid_uuid_in_set_bot_token(self, project_repo):
        with pytest.raises(ValueError):
            await project_repo.set_bot_token("invalid-uuid", "token")

    @pytest.mark.asyncio
    async def test_invalid_uuid_in_project_exists(self, project_repo):
        with pytest.raises(ValueError):
            await project_repo.project_exists("invalid-uuid")

    # ------------------------------------------------------------------
    # Database errors
    # ------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_connection_error(self, project_repo, mock_pool):
        mock_pool.acquire.side_effect = asyncpg.exceptions.ConnectionDoesNotExistError("conn closed")
        with pytest.raises(asyncpg.exceptions.ConnectionDoesNotExistError):
            await project_repo.get_project_settings(str(uuid4()))

    @pytest.mark.asyncio
    async def test_undefined_table_error(self, project_repo, mock_pool):
        mock_pool.mock_conn.fetchrow = AsyncMock(side_effect=asyncpg.exceptions.UndefinedTableError("no table"))
        with pytest.raises(asyncpg.exceptions.UndefinedTableError):
            await project_repo.get_project_settings(str(uuid4()))
