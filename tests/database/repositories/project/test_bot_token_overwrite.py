from uuid import uuid4

import pytest

from src.infrastructure.db.repositories.project import ProjectRepository
from src.infrastructure.db.repositories.project.project_tokens import (
    ProjectTokenRepository,
)


class FakeConnection:
    def __init__(self):
        self.execute_calls = []
        self.fetchval_calls = []
        self.fetchval_result = None

    async def execute(self, query, *args):
        self.execute_calls.append((query, args))
        return "UPDATE 1"

    async def fetchval(self, query, *args):
        self.fetchval_calls.append((query, args))
        return self.fetchval_result


class FakeAcquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakePool:
    def __init__(self):
        self.conn = FakeConnection()

    def acquire(self):
        return FakeAcquire(self.conn)


class TokenRepoProbe(ProjectTokenRepository):
    def __init__(self):
        self.fake_pool = FakePool()
        super().__init__(self.fake_pool)
        self.username_lookups = []

    def _encrypt_if_present(self, token):
        if token is None:
            return None
        return f"encrypted::{token}"

    async def _get_bot_username(self, token):
        self.username_lookups.append(token)
        return f"username_for_{token}"


def _joined_execute_log(repo: TokenRepoProbe) -> str:
    chunks = []
    for query, args in repo.fake_pool.conn.execute_calls:
        chunks.append(query)
        chunks.extend(repr(arg) for arg in args)
    return "\\n".join(chunks)


def _last_execute(repo: TokenRepoProbe):
    assert repo.fake_pool.conn.execute_calls, "expected at least one UPDATE"
    return repo.fake_pool.conn.execute_calls[-1]


def _assert_last_write_contains(
    repo: TokenRepoProbe,
    *,
    encrypted_token,
    username,
    db_token_column: str,
    db_username_column: str,
) -> None:
    query, args = _last_execute(repo)
    text = query.lower()

    assert "update" in text
    assert "projects" in text
    assert db_token_column in text
    assert db_username_column in text
    assert encrypted_token in args
    assert username in args


def _assert_last_write_clears_column(repo: TokenRepoProbe, column: str) -> None:
    query, _ = _last_execute(repo)
    assert f"{column} = null" in query.lower()


def test_project_repository_facade_exposes_token_control_contract():
    assert issubclass(ProjectRepository, ProjectTokenRepository)
    assert hasattr(ProjectRepository, "set_bot_token")
    assert hasattr(ProjectRepository, "set_manager_bot_token")
    assert hasattr(ProjectRepository, "set_client_telegram_bot_id")
    assert hasattr(ProjectRepository, "set_manager_telegram_bot_id")
    assert hasattr(ProjectRepository, "get_client_telegram_bot_id")
    assert hasattr(ProjectRepository, "get_manager_telegram_bot_id")
    assert hasattr(ProjectRepository, "clear_bot_token")
    assert hasattr(ProjectRepository, "clear_manager_token")


@pytest.mark.asyncio
async def test_client_bot_attach_overwrites_previous_token_with_new_token():
    repo = TokenRepoProbe()
    project_id = str(uuid4())

    await repo.set_bot_token(project_id, "old-client-token")
    await repo.set_bot_token(project_id, "new-client-token")

    log = _joined_execute_log(repo)

    assert "encrypted::old-client-token" in log
    assert "username_for_old-client-token" in log
    assert "encrypted::new-client-token" in log
    assert "username_for_new-client-token" in log
    assert repo.username_lookups == ["old-client-token", "new-client-token"]

    _assert_last_write_contains(
        repo,
        encrypted_token="encrypted::new-client-token",
        username="username_for_new-client-token",
        db_token_column="bot_token",
        db_username_column="client_bot_username",
    )
    _assert_last_write_clears_column(repo, "client_telegram_bot_id")


@pytest.mark.asyncio
async def test_manager_bot_attach_overwrites_previous_token_with_new_token():
    repo = TokenRepoProbe()
    project_id = str(uuid4())

    await repo.set_manager_bot_token(project_id, "old-manager-token")
    await repo.set_manager_bot_token(project_id, "new-manager-token")

    log = _joined_execute_log(repo)

    assert "encrypted::old-manager-token" in log
    assert "username_for_old-manager-token" in log
    assert "encrypted::new-manager-token" in log
    assert "username_for_new-manager-token" in log
    assert repo.username_lookups == ["old-manager-token", "new-manager-token"]

    _assert_last_write_contains(
        repo,
        encrypted_token="encrypted::new-manager-token",
        username="username_for_new-manager-token",
        db_token_column="manager_bot_token",
        db_username_column="manager_bot_username",
    )
    _assert_last_write_clears_column(repo, "manager_telegram_bot_id")


@pytest.mark.asyncio
async def test_client_bot_clear_writes_null_token_and_null_username():
    repo = TokenRepoProbe()
    project_id = str(uuid4())

    await repo.clear_bot_token(project_id)

    query, args = _last_execute(repo)
    lowered = query.lower()

    assert "update" in lowered
    assert "projects" in lowered
    assert "bot_token" in lowered
    assert "client_bot_username" in lowered
    assert "client_telegram_bot_id = null" in lowered
    assert args[0] is None
    assert args[1] is None
    assert repo.username_lookups == []


@pytest.mark.asyncio
async def test_manager_bot_clear_writes_null_token_and_null_username():
    repo = TokenRepoProbe()
    project_id = str(uuid4())

    await repo.clear_manager_token(project_id)

    query, args = _last_execute(repo)
    lowered = query.lower()

    assert "update" in lowered
    assert "projects" in lowered
    assert "manager_bot_token" in lowered
    assert "manager_bot_username" in lowered
    assert "manager_telegram_bot_id = null" in lowered
    assert args[0] is None
    assert args[1] is None
    assert repo.username_lookups == []


@pytest.mark.asyncio
async def test_client_telegram_bot_id_helpers_use_numeric_id_column_only():
    repo = TokenRepoProbe()
    project_id = str(uuid4())

    await repo.set_client_telegram_bot_id(project_id, 123456)
    repo.fake_pool.conn.fetchval_result = 123456
    result = await repo.get_client_telegram_bot_id(project_id)

    query, args = _last_execute(repo)
    assert "client_telegram_bot_id" in query
    assert "bot_token" not in query
    assert "webhook_secret" not in query
    assert args[0] == 123456
    fetch_query, _ = repo.fake_pool.conn.fetchval_calls[-1]
    assert "client_telegram_bot_id" in fetch_query
    assert result == 123456


@pytest.mark.asyncio
async def test_client_token_replacement_clears_previous_numeric_bot_id_until_getme_sets_new_id():
    repo = TokenRepoProbe()
    project_id = str(uuid4())

    await repo.set_client_telegram_bot_id(project_id, 111)
    await repo.set_bot_token(project_id, "replacement-token")

    set_id_query, set_id_args = repo.fake_pool.conn.execute_calls[0]
    replacement_query, replacement_args = repo.fake_pool.conn.execute_calls[1]
    assert "client_telegram_bot_id = $1" in set_id_query.lower()
    assert set_id_args[0] == 111
    assert "client_telegram_bot_id = null" in replacement_query.lower()
    assert "encrypted::replacement-token" in replacement_args

    await repo.set_client_telegram_bot_id(project_id, 222)
    final_query, final_args = _last_execute(repo)
    assert "client_telegram_bot_id = $1" in final_query.lower()
    assert final_args[0] == 222


@pytest.mark.asyncio
async def test_client_unfinished_onboarding_leaves_numeric_bot_id_null_after_token_write():
    repo = TokenRepoProbe()
    project_id = str(uuid4())

    await repo.set_bot_token(project_id, "replacement-token")

    query, _ = _last_execute(repo)
    assert "client_telegram_bot_id = null" in query.lower()
    assert "client_telegram_bot_id = $1" not in query.lower()


@pytest.mark.asyncio
async def test_manager_telegram_bot_id_helpers_use_numeric_id_column_only():
    repo = TokenRepoProbe()
    project_id = str(uuid4())

    await repo.set_manager_telegram_bot_id(project_id, 987654)
    repo.fake_pool.conn.fetchval_result = 987654
    result = await repo.get_manager_telegram_bot_id(project_id)

    query, args = _last_execute(repo)
    assert "manager_telegram_bot_id" in query
    assert "manager_bot_token" not in query
    assert "manager_webhook_secret" not in query
    assert args[0] == 987654
    fetch_query, _ = repo.fake_pool.conn.fetchval_calls[-1]
    assert "manager_telegram_bot_id" in fetch_query
    assert result == 987654


@pytest.mark.asyncio
async def test_manager_token_replacement_clears_previous_numeric_bot_id_until_getme_sets_new_id():
    repo = TokenRepoProbe()
    project_id = str(uuid4())

    await repo.set_manager_telegram_bot_id(project_id, 333)
    await repo.set_manager_bot_token(project_id, "replacement-token")

    set_id_query, set_id_args = repo.fake_pool.conn.execute_calls[0]
    replacement_query, replacement_args = repo.fake_pool.conn.execute_calls[1]
    assert "manager_telegram_bot_id = $1" in set_id_query.lower()
    assert set_id_args[0] == 333
    assert "manager_telegram_bot_id = null" in replacement_query.lower()
    assert "encrypted::replacement-token" in replacement_args

    await repo.set_manager_telegram_bot_id(project_id, 444)
    final_query, final_args = _last_execute(repo)
    assert "manager_telegram_bot_id = $1" in final_query.lower()
    assert final_args[0] == 444


@pytest.mark.asyncio
async def test_manager_unfinished_onboarding_leaves_numeric_bot_id_null_after_token_write():
    repo = TokenRepoProbe()
    project_id = str(uuid4())

    await repo.set_manager_bot_token(project_id, "replacement-token")

    query, _ = _last_execute(repo)
    assert "manager_telegram_bot_id = null" in query.lower()
    assert "manager_telegram_bot_id = $1" not in query.lower()


@pytest.mark.asyncio
@pytest.mark.parametrize("telegram_bot_id", [123456, None])
async def test_project_telegram_bot_id_helpers_accept_valid_ids(telegram_bot_id):
    repo = TokenRepoProbe()
    project_id = str(uuid4())

    await repo.set_client_telegram_bot_id(project_id, telegram_bot_id)
    await repo.set_manager_telegram_bot_id(project_id, telegram_bot_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("telegram_bot_id", [0, -1])
async def test_project_telegram_bot_id_helpers_reject_zero_and_negative_ids(
    telegram_bot_id,
):
    repo = TokenRepoProbe()
    project_id = str(uuid4())

    with pytest.raises(ValueError):
        await repo.set_client_telegram_bot_id(project_id, telegram_bot_id)
    with pytest.raises(ValueError):
        await repo.set_manager_telegram_bot_id(project_id, telegram_bot_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("telegram_bot_id", [True, False])
async def test_project_telegram_bot_id_helpers_reject_bool_ids(telegram_bot_id):
    repo = TokenRepoProbe()
    project_id = str(uuid4())

    with pytest.raises(TypeError):
        await repo.set_client_telegram_bot_id(project_id, telegram_bot_id)
    with pytest.raises(TypeError):
        await repo.set_manager_telegram_bot_id(project_id, telegram_bot_id)
