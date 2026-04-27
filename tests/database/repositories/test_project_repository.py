import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4
from datetime import datetime
import asyncpg

from src.infrastructure.db.repositories.project import ProjectRepository


@pytest.fixture
def mock_pool():
    pool = AsyncMock()
    mock_conn = AsyncMock()
    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_conn
    mock_cm.__aexit__.return_value = None
    pool.acquire = MagicMock(return_value=mock_cm)

    transaction_cm = AsyncMock()
    transaction_cm.__aenter__.return_value = None
    transaction_cm.__aexit__.return_value = None
    mock_conn.transaction = MagicMock(return_value=transaction_cm)

    pool.mock_conn = mock_conn
    return pool


@pytest.fixture
def project_repo(mock_pool):
    return ProjectRepository(mock_pool)


class TestProjectRepository:
    def test_init(self, project_repo, mock_pool):
        assert project_repo.pool is mock_pool

    @pytest.mark.asyncio
    async def test_get_project_settings_success(self, project_repo, mock_pool):
        project_id = str(uuid4())
        row = {
            "system_prompt": "prompt",
            "bot_token": "encrypted_token",
            "webhook_url": "https://example.com",
            "manager_bot_token": "encrypted_manager_token",
            "webhook_secret": "secret",
            "is_pro_mode": True,
            "client_bot_username": "client_bot",
            "manager_bot_username": "manager_bot",
        }
        manager_rows = [{"manager_chat_id": "123"}, {"manager_chat_id": "456"}]

        mock_pool.mock_conn.fetchrow = AsyncMock(return_value=row)
        mock_pool.mock_conn.fetch = AsyncMock(return_value=manager_rows)

        with patch(
            "src.infrastructure.db.repositories.project.base.decrypt_token",
            side_effect=lambda x: f"decrypted_{x}" if x else None,
        ):
            result = await project_repo.get_project_settings(project_id)

        assert result.system_prompt == "prompt"
        assert result.bot_token == "decrypted_encrypted_token"
        assert result.manager_bot_token == "decrypted_encrypted_manager_token"
        assert result.webhook_secret == "secret"
        assert result.is_pro_mode is True
        assert result.client_bot_username == "client_bot"
        assert result.manager_bot_username == "manager_bot"
        assert result.manager_notification_targets == ["123", "456"]
        assert result.manager_chat_ids == ["123", "456"]

    @pytest.mark.asyncio
    async def test_get_project_settings_not_found(self, project_repo, mock_pool):
        mock_pool.mock_conn.fetchrow = AsyncMock(return_value=None)

        result = await project_repo.get_project_settings(str(uuid4()))

        assert result.to_record() == {
            "system_prompt": None,
            "bot_token": None,
            "webhook_url": None,
            "manager_bot_token": None,
            "webhook_secret": None,
            "is_pro_mode": False,
            "client_bot_username": None,
            "manager_bot_username": None,
            "manager_notification_targets": [],
            "manager_chat_ids": [],
        }

    @pytest.mark.asyncio
    async def test_get_project_settings_no_managers(self, project_repo, mock_pool):
        row = {
            "system_prompt": "prompt",
            "bot_token": None,
            "webhook_url": None,
            "manager_bot_token": None,
            "webhook_secret": None,
            "is_pro_mode": False,
            "client_bot_username": None,
            "manager_bot_username": None,
        }

        mock_pool.mock_conn.fetchrow = AsyncMock(return_value=row)
        mock_pool.mock_conn.fetch = AsyncMock(return_value=[])

        with patch(
            "src.infrastructure.db.repositories.project.base.decrypt_token",
            return_value=None,
        ):
            result = await project_repo.get_project_settings(str(uuid4()))

        assert result.manager_notification_targets == []
        assert result.manager_chat_ids == []

    @pytest.mark.asyncio
    async def test_get_bot_token_success(self, project_repo, mock_pool):
        project_id = str(uuid4())
        mock_pool.mock_conn.fetchval = AsyncMock(return_value="encrypted_token")

        with patch(
            "src.infrastructure.db.repositories.project.base.decrypt_token",
            return_value="decrypted_token",
        ):
            token = await project_repo.get_bot_token(project_id)

        assert token == "decrypted_token"

    @pytest.mark.asyncio
    async def test_get_bot_token_none(self, project_repo, mock_pool):
        mock_pool.mock_conn.fetchval = AsyncMock(return_value=None)

        token = await project_repo.get_bot_token(str(uuid4()))

        assert token is None

    @pytest.mark.asyncio
    async def test_set_bot_token_with_token(self, project_repo, mock_pool):
        project_id = str(uuid4())
        mock_pool.mock_conn.execute = AsyncMock()

        with patch(
            "src.infrastructure.db.repositories.project.base.encrypt_token",
            return_value="encrypted_token",
        ):
            with patch.object(
                project_repo,
                "_get_bot_username",
                AsyncMock(return_value="bot_username"),
            ):
                await project_repo.set_bot_token(project_id, "real_token")

        mock_pool.mock_conn.execute.assert_awaited_once()
        args = mock_pool.mock_conn.execute.await_args.args
        assert "UPDATE projects" in args[0]
        assert args[1:] == ("encrypted_token", "bot_username", UUID(project_id))

    @pytest.mark.asyncio
    async def test_set_bot_token_with_none(self, project_repo, mock_pool):
        project_id = str(uuid4())
        mock_pool.mock_conn.execute = AsyncMock()

        with patch(
            "src.infrastructure.db.repositories.project.base.encrypt_token",
            return_value=None,
        ):
            await project_repo.set_bot_token(project_id, None)

        args = mock_pool.mock_conn.execute.await_args.args
        assert args[1:] == (None, None, UUID(project_id))

    @pytest.mark.asyncio
    async def test_get_manager_bot_token_success(self, project_repo, mock_pool):
        project_id = str(uuid4())
        mock_pool.mock_conn.fetchval = AsyncMock(return_value="encrypted")

        with patch(
            "src.infrastructure.db.repositories.project.base.decrypt_token",
            return_value="decrypted",
        ):
            token = await project_repo.get_manager_bot_token(project_id)

        assert token == "decrypted"

    @pytest.mark.asyncio
    async def test_get_manager_bot_token_none(self, project_repo, mock_pool):
        mock_pool.mock_conn.fetchval = AsyncMock(return_value=None)

        token = await project_repo.get_manager_bot_token(str(uuid4()))

        assert token is None

    @pytest.mark.asyncio
    async def test_set_manager_bot_token_with_token(self, project_repo, mock_pool):
        project_id = str(uuid4())
        mock_pool.mock_conn.execute = AsyncMock()

        with patch(
            "src.infrastructure.db.repositories.project.base.encrypt_token",
            return_value="encrypted_token",
        ):
            with patch.object(
                project_repo,
                "_get_bot_username",
                AsyncMock(return_value="manager_username"),
            ):
                await project_repo.set_manager_bot_token(project_id, "real_token")

        args = mock_pool.mock_conn.execute.await_args.args
        assert args[1:] == ("encrypted_token", "manager_username", UUID(project_id))

    @pytest.mark.asyncio
    async def test_set_manager_bot_token_with_none(self, project_repo, mock_pool):
        project_id = str(uuid4())
        mock_pool.mock_conn.execute = AsyncMock()

        with patch(
            "src.infrastructure.db.repositories.project.base.encrypt_token",
            return_value=None,
        ):
            await project_repo.set_manager_bot_token(project_id, None)

        args = mock_pool.mock_conn.execute.await_args.args
        assert args[1:] == (None, None, UUID(project_id))

    @pytest.mark.asyncio
    async def test_get_webhook_secret(self, project_repo, mock_pool):
        mock_pool.mock_conn.fetchval = AsyncMock(return_value="secret")

        secret = await project_repo.get_webhook_secret(str(uuid4()))

        assert secret == "secret"

    @pytest.mark.asyncio
    async def test_set_webhook_secret(self, project_repo, mock_pool):
        project_id = str(uuid4())
        mock_pool.mock_conn.execute = AsyncMock()

        await project_repo.set_webhook_secret(project_id, "new_secret")

        args = mock_pool.mock_conn.execute.await_args.args
        assert args[1:] == ("new_secret", UUID(project_id))

    @pytest.mark.asyncio
    async def test_get_manager_notification_targets(self, project_repo, mock_pool):
        rows = [
            {"user_id": uuid4(), "manager_chat_id": "111"},
            {"user_id": uuid4(), "manager_chat_id": "222"},
        ]
        mock_pool.mock_conn.fetch = AsyncMock(return_value=rows)

        result = await project_repo.get_manager_notification_targets(str(uuid4()))

        assert result == ["111", "222"]

    @pytest.mark.asyncio
    async def test_get_manager_notification_recipients_returns_canonical_targets(
        self, project_repo, mock_pool
    ):
        project_id = str(uuid4())
        user_id = uuid4()
        mock_pool.mock_conn.fetch = AsyncMock(
            return_value=[{"user_id": user_id, "manager_chat_id": "111"}]
        )

        result = await project_repo.get_manager_notification_recipients(project_id)

        assert len(result) == 1
        assert result[0].user_id == str(user_id)
        assert result[0].telegram_chat_id == "111"

    @pytest.mark.asyncio
    async def test_add_manager_by_telegram_identity_uses_project_members_for_platform_user(
        self, project_repo, mock_pool
    ):
        project_id = str(uuid4())
        user_id = uuid4()
        mock_pool.mock_conn.fetchrow = AsyncMock(return_value={"id": user_id})
        mock_pool.mock_conn.execute = AsyncMock()

        result = await project_repo.add_manager_by_telegram_identity(project_id, "123")

        assert result.to_record() == {
            "status": "added",
            "storage": "project_members",
            "user_id": str(user_id),
            "role": "manager",
        }

    @pytest.mark.asyncio
    async def test_add_manager_by_telegram_identity_creates_platform_user_when_missing(
        self, project_repo, mock_pool
    ):
        user_id = uuid4()
        mock_pool.mock_conn.fetchrow = AsyncMock(return_value=None)
        mock_pool.mock_conn.fetchval = AsyncMock(return_value=user_id)
        mock_pool.mock_conn.execute = AsyncMock()

        result = await project_repo.add_manager_by_telegram_identity(
            str(uuid4()), "123"
        )

        assert result.status == "added"
        assert result.user_id == str(user_id)
        assert result.role == "manager"

    @pytest.mark.asyncio
    async def test_remove_manager_by_telegram_identity_removes_member(
        self, project_repo, mock_pool
    ):
        mock_pool.mock_conn.execute = AsyncMock()

        await project_repo.remove_manager_by_telegram_identity(str(uuid4()), "123")

        mock_pool.mock_conn.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_resolve_manager_user_id_by_telegram_uses_membership(
        self, project_repo, mock_pool
    ):
        user_id = uuid4()
        mock_pool.mock_conn.fetchval = AsyncMock(return_value=user_id)

        result = await project_repo.resolve_manager_user_id_by_telegram(
            str(uuid4()), "123"
        )

        assert result == str(user_id)

    @pytest.mark.asyncio
    async def test_get_user_display_name_prefers_full_name(
        self, project_repo, mock_pool
    ):
        user_id = str(uuid4())
        mock_pool.mock_conn.fetchrow = AsyncMock(
            return_value={
                "full_name": "Alice Manager",
                "username": "alice",
                "email": "alice@example.com",
            }
        )

        result = await project_repo.get_user_display_name(user_id)

        assert result == "Alice Manager"

    @pytest.mark.asyncio
    async def test_set_pro_mode(self, project_repo, mock_pool):
        project_id = str(uuid4())
        mock_pool.mock_conn.execute = AsyncMock()

        await project_repo.set_pro_mode(project_id, True)

        args = mock_pool.mock_conn.execute.await_args.args
        assert args[1:] == (True, UUID(project_id))

    @pytest.mark.asyncio
    async def test_get_is_pro_mode(self, project_repo, mock_pool):
        mock_pool.mock_conn.fetchval = AsyncMock(return_value=True)

        result = await project_repo.get_is_pro_mode(str(uuid4()))

        assert result is True

    @pytest.mark.asyncio
    async def test_find_project_by_manager_token_found(self, project_repo, mock_pool):
        rows = [
            {"id": uuid4(), "manager_bot_token": "enc1"},
            {"id": uuid4(), "manager_bot_token": "enc2"},
        ]
        mock_pool.mock_conn.fetch = AsyncMock(return_value=rows)

        with patch(
            "src.infrastructure.db.repositories.project.base.decrypt_token",
            side_effect=lambda x: f"decrypted_{x}" if x else None,
        ):
            result = await project_repo.find_project_by_manager_token("decrypted_enc2")

        assert result == str(rows[1]["id"])

    @pytest.mark.asyncio
    async def test_find_project_by_manager_token_not_found(
        self, project_repo, mock_pool
    ):
        mock_pool.mock_conn.fetch = AsyncMock(
            return_value=[
                {"id": uuid4(), "manager_bot_token": "enc1"},
            ]
        )

        with patch(
            "src.infrastructure.db.repositories.project.base.decrypt_token",
            return_value="different",
        ):
            result = await project_repo.find_project_by_manager_token("nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_find_project_by_manager_token_empty(self, project_repo, mock_pool):
        mock_pool.mock_conn.fetch = AsyncMock(return_value=[])

        result = await project_repo.find_project_by_manager_token("token")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_manager_webhook_secret(self, project_repo, mock_pool):
        mock_pool.mock_conn.fetchval = AsyncMock(return_value="secret")

        secret = await project_repo.get_manager_webhook_secret(str(uuid4()))

        assert secret == "secret"

    @pytest.mark.asyncio
    async def test_set_manager_webhook_secret(self, project_repo, mock_pool):
        project_id = str(uuid4())
        mock_pool.mock_conn.execute = AsyncMock()

        await project_repo.set_manager_webhook_secret(project_id, "new_secret")

        args = mock_pool.mock_conn.execute.await_args.args
        assert args[1:] == ("new_secret", UUID(project_id))

    @pytest.mark.asyncio
    async def test_find_project_by_manager_webhook_secret_found(
        self, project_repo, mock_pool
    ):
        row = {"id": uuid4()}
        mock_pool.mock_conn.fetchrow = AsyncMock(return_value=row)

        result = await project_repo.find_project_by_manager_webhook_secret("secret")

        assert result == str(row["id"])

    @pytest.mark.asyncio
    async def test_find_project_by_manager_webhook_secret_not_found(
        self, project_repo, mock_pool
    ):
        mock_pool.mock_conn.fetchrow = AsyncMock(return_value=None)

        result = await project_repo.find_project_by_manager_webhook_secret("secret")

        assert result is None

    @pytest.mark.asyncio
    async def test_project_exists_true(self, project_repo, mock_pool):
        mock_pool.mock_conn.fetchval = AsyncMock(return_value=1)

        result = await project_repo.project_exists(str(uuid4()))

        assert result is True

    @pytest.mark.asyncio
    async def test_project_exists_false(self, project_repo, mock_pool):
        mock_pool.mock_conn.fetchval = AsyncMock(return_value=None)

        result = await project_repo.project_exists(str(uuid4()))

        assert result is False

    @pytest.mark.asyncio
    async def test_create_project_with_user_id(self, project_repo, mock_pool):
        user_id = str(uuid4())
        project_id = uuid4()
        mock_pool.mock_conn.fetchval = AsyncMock(return_value=project_id)
        mock_pool.mock_conn.execute = AsyncMock()

        result = await project_repo.create_project_with_user_id(user_id, "Test Project")

        assert result == str(project_id)

    @pytest.mark.asyncio
    async def test_get_all_projects(self, project_repo, mock_pool):
        rows = [
            {
                "id": uuid4(),
                "user_id": uuid4(),
                "name": "p1",
                "is_pro_mode": False,
                "created_at": datetime.now(),
                "updated_at": datetime.now(),
            },
            {
                "id": uuid4(),
                "user_id": None,
                "name": "p2",
                "is_pro_mode": True,
                "created_at": datetime.now(),
                "updated_at": datetime.now(),
            },
        ]
        mock_pool.mock_conn.fetch = AsyncMock(return_value=rows)

        result = await project_repo.get_all_projects()

        assert len(result) == 2
        assert result[0].id == str(rows[0]["id"])
        assert result[0].user_id == str(rows[0]["user_id"])
        assert result[1].user_id is None

    @pytest.mark.asyncio
    async def test_get_project_view_found(self, project_repo, mock_pool):
        project_id = str(uuid4())
        user_id = str(uuid4())
        row = {
            "id": project_id,
            "user_id": user_id,
            "name": "Test",
            "is_pro_mode": True,
            "created_at": datetime.now(),
            "updated_at": datetime.now(),
            "client_bot_username": "client_bot",
            "manager_bot_username": "manager_bot",
        }
        mock_pool.mock_conn.fetchrow = AsyncMock(return_value=row)

        result = await project_repo.get_project_view(project_id)

        assert result is not None
        assert result.id == project_id
        assert result.user_id == user_id
        assert result.name == "Test"
        assert result.is_pro_mode is True
        assert result.client_bot_username == "client_bot"
        assert result.manager_bot_username == "manager_bot"

    @pytest.mark.asyncio
    async def test_get_project_view_not_found(self, project_repo, mock_pool):
        mock_pool.mock_conn.fetchrow = AsyncMock(return_value=None)

        result = await project_repo.get_project_view(str(uuid4()))

        assert result is None

    @pytest.mark.asyncio
    async def test_update_project(self, project_repo, mock_pool):
        project_id = str(uuid4())
        mock_pool.mock_conn.execute = AsyncMock()

        await project_repo.update_project(project_id, "New Name")

        args = mock_pool.mock_conn.execute.await_args.args
        assert args[1:] == ("New Name", UUID(project_id))

    @pytest.mark.asyncio
    async def test_update_project_none_name(self, project_repo, mock_pool):
        await project_repo.update_project(str(uuid4()), None)

        mock_pool.mock_conn.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_project(self, project_repo, mock_pool):
        project_id = str(uuid4())
        mock_pool.mock_conn.execute = AsyncMock()

        await project_repo.delete_project(project_id)

        args = mock_pool.mock_conn.execute.await_args.args
        assert args[1:] == (UUID(project_id),)

    @pytest.mark.asyncio
    async def test_get_projects_by_user_id(self, project_repo, mock_pool):
        user_id = str(uuid4())
        rows = [
            {
                "id": uuid4(),
                "name": "p1",
                "is_pro_mode": False,
                "created_at": datetime.now(),
                "updated_at": datetime.now(),
                "client_bot_username": None,
                "manager_bot_username": None,
            }
        ]
        mock_pool.mock_conn.fetch = AsyncMock(return_value=rows)

        result = await project_repo.get_projects_by_user_id(user_id)

        assert len(result) == 1
        assert result[0].id == str(rows[0]["id"])
        assert result[0].user_id == user_id
        assert result[0].name == "p1"

    @pytest.mark.asyncio
    async def test_get_projects_for_user_view(self, project_repo, mock_pool):
        user_id = str(uuid4())
        rows = [
            {
                "id": uuid4(),
                "name": "p1",
                "is_pro_mode": False,
                "created_at": datetime.now(),
                "updated_at": datetime.now(),
                "client_bot_username": "client_bot",
                "manager_bot_username": "manager_bot",
                "user_id": UUID(user_id),
                "access_role": "owner",
            }
        ]
        mock_pool.mock_conn.fetch = AsyncMock(return_value=rows)

        result = await project_repo.get_projects_for_user_view(user_id)

        assert len(result) == 1
        assert result[0].id == str(rows[0]["id"])
        assert result[0].user_id == user_id
        assert result[0].access_role == "owner"

    @pytest.mark.asyncio
    async def test_get_project_members_includes_owner_when_missing(
        self, project_repo, mock_pool
    ):
        project_id = str(uuid4())
        owner_user_id = uuid4()
        rows = [
            {
                "id": owner_user_id,
                "project_id": UUID(project_id),
                "user_id": owner_user_id,
                "role": "owner",
                "created_at": datetime.now(),
                "telegram_id": 123456,
                "username": "owner",
                "full_name": "Owner User",
                "email": "owner@example.com",
            }
        ]
        mock_pool.mock_conn.fetch = AsyncMock(return_value=rows)

        result = await project_repo.get_project_members_view(project_id)

        assert len(result) == 1
        assert result[0].user_id == str(owner_user_id)
        assert result[0].role == "owner"
        assert result[0].telegram_id == 123456

    @pytest.mark.asyncio
    async def test_get_project_configuration_normalizes_blocks(
        self, project_repo, mock_pool
    ):
        project_id = uuid4()
        integration_id = uuid4()
        channel_id = uuid4()
        prompt_id = uuid4()
        created_at = datetime.now()
        updated_at = datetime.now()

        mock_pool.mock_conn.fetchrow = AsyncMock(
            side_effect=[
                {
                    "brand_name": "Acme",
                    "industry": "services",
                    "tone_of_voice": "warm",
                    "default_language": "ru",
                    "default_timezone": "Europe/Moscow",
                    "system_prompt_override": None,
                    "created_at": created_at,
                    "updated_at": updated_at,
                },
                {
                    "escalation_policy_json": {"mode": "manager"},
                    "routing_policy_json": {},
                    "crm_policy_json": {},
                    "response_policy_json": {},
                    "privacy_policy_json": {},
                    "created_at": created_at,
                    "updated_at": updated_at,
                },
                {
                    "monthly_token_limit": 100000,
                    "requests_per_minute": 30,
                    "max_concurrent_threads": 5,
                    "priority": 1,
                    "fallback_model": "llama-3.1-8b-instant",
                    "created_at": created_at,
                    "updated_at": updated_at,
                },
            ]
        )
        mock_pool.mock_conn.fetch = AsyncMock(
            side_effect=[
                [
                    {
                        "id": integration_id,
                        "provider": "amo_crm",
                        "status": "active",
                        "config_json": {"base_url": "https://crm.example"},
                        "created_at": created_at,
                        "updated_at": updated_at,
                    }
                ],
                [
                    {
                        "id": channel_id,
                        "kind": "client",
                        "provider": "telegram",
                        "status": "active",
                        "config_json": {"bot": "client"},
                        "created_at": created_at,
                        "updated_at": updated_at,
                    }
                ],
                [
                    {
                        "id": prompt_id,
                        "name": "default",
                        "prompt_json": {"system": "hello"},
                        "version": 1,
                        "is_active": True,
                        "created_at": created_at,
                        "updated_at": updated_at,
                    }
                ],
            ]
        )

        result = await project_repo.get_project_configuration_view(project_id)

        assert result.project_id == str(project_id)
        assert result.settings["brand_name"] == "Acme"
        assert result.policies["escalation_policy_json"] == {"mode": "manager"}
        assert result.limit_profile["requests_per_minute"] == 30
        assert result.integrations[0].id == str(integration_id)
        assert result.channels[0].id == str(channel_id)
        assert result.prompt_versions[0].id == str(prompt_id)
        assert result.integrations[0].created_at == created_at.isoformat()

    @pytest.mark.asyncio
    async def test_update_project_settings(self, project_repo, mock_pool):
        project_id = str(uuid4())
        mock_pool.mock_conn.execute = AsyncMock()

        await project_repo.update_project_settings(
            project_id,
            {
                "brand_name": "Acme",
                "industry": "services",
                "tone_of_voice": "warm",
                "default_language": "ru",
                "default_timezone": "Europe/Moscow",
                "system_prompt_override": "Custom prompt",
            },
        )

        args = mock_pool.mock_conn.execute.await_args.args
        assert "INSERT INTO project_settings" in args[0]
        assert args[1] == UUID(project_id)

    @pytest.mark.asyncio
    async def test_update_project_policies(self, project_repo, mock_pool):
        project_id = str(uuid4())
        mock_pool.mock_conn.execute = AsyncMock()

        await project_repo.update_project_policies(
            project_id,
            {
                "escalation_policy_json": {"after_minutes": 3},
                "routing_policy_json": {"default": "manager"},
                "crm_policy_json": {"sync": True},
                "response_policy_json": {"max_length": 500},
                "privacy_policy_json": {"mask_phone": True},
            },
        )

        args = mock_pool.mock_conn.execute.await_args.args
        assert "INSERT INTO project_policies" in args[0]
        assert args[1] == UUID(project_id)

    @pytest.mark.asyncio
    async def test_update_project_limit_profile(self, project_repo, mock_pool):
        project_id = str(uuid4())
        mock_pool.mock_conn.execute = AsyncMock()

        await project_repo.update_project_limit_profile(
            project_id,
            {
                "monthly_token_limit": 100000,
                "requests_per_minute": 60,
                "max_concurrent_threads": 10,
                "priority": 2,
                "fallback_model": "llama-3.1-8b-instant",
            },
        )

        args = mock_pool.mock_conn.execute.await_args.args
        assert "INSERT INTO project_limit_profiles" in args[0]
        assert args[1] == UUID(project_id)

    @pytest.mark.asyncio
    async def test_upsert_project_integration_normalizes_result(
        self, project_repo, mock_pool
    ):
        project_id = uuid4()
        integration_id = uuid4()
        created_at = datetime.now()
        updated_at = datetime.now()

        mock_pool.mock_conn.fetchrow = AsyncMock(
            return_value={
                "id": integration_id,
                "project_id": project_id,
                "provider": "amo_crm",
                "status": "active",
                "config_json": {"webhook_url": "https://crm.example/hook"},
                "created_at": created_at,
                "updated_at": updated_at,
            }
        )

        result = await project_repo.upsert_project_integration(
            project_id,
            provider="amo_crm",
            status="active",
            config_json={"webhook_url": "https://crm.example/hook"},
            credentials_encrypted="encrypted",
        )

        assert result.id == str(integration_id)
        assert result.project_id == str(project_id)
        assert result.provider == "amo_crm"
        assert result.created_at == created_at.isoformat()
        assert result.updated_at == updated_at.isoformat()

    @pytest.mark.asyncio
    async def test_upsert_project_channel_normalizes_result(
        self, project_repo, mock_pool
    ):
        project_id = uuid4()
        channel_id = uuid4()
        created_at = datetime.now()
        updated_at = datetime.now()

        mock_pool.mock_conn.fetchrow = AsyncMock(
            return_value={
                "id": channel_id,
                "project_id": project_id,
                "kind": "widget",
                "provider": "web",
                "status": "active",
                "config_json": {"allowed_origin": "https://site.example"},
                "created_at": created_at,
                "updated_at": updated_at,
            }
        )

        result = await project_repo.upsert_project_channel(
            project_id,
            kind="widget",
            provider="web",
            status="active",
            config_json={"allowed_origin": "https://site.example"},
        )

        assert result.id == str(channel_id)
        assert result.project_id == str(project_id)
        assert result.kind == "widget"
        assert result.provider == "web"
        assert result.created_at == created_at.isoformat()

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

    @pytest.mark.asyncio
    async def test_connection_error(self, project_repo, mock_pool):
        mock_pool.acquire.side_effect = asyncpg.exceptions.ConnectionDoesNotExistError(
            "conn closed"
        )

        with pytest.raises(asyncpg.exceptions.ConnectionDoesNotExistError):
            await project_repo.get_project_settings(str(uuid4()))

    @pytest.mark.asyncio
    async def test_undefined_table_error(self, project_repo, mock_pool):
        mock_pool.mock_conn.fetchrow = AsyncMock(
            side_effect=asyncpg.exceptions.UndefinedTableError("no table")
        )

        with pytest.raises(asyncpg.exceptions.UndefinedTableError):
            await project_repo.get_project_settings(str(uuid4()))
