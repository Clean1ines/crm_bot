from uuid import uuid4

import pytest

from src.infrastructure.db.repositories.project import ProjectRepository
from src.infrastructure.db.repositories.project.project_tokens import (
    ProjectTokenRepository,
)


class FakeConnection:
    def __init__(self):
        self.execute_calls = []

    async def execute(self, query, *args):
        self.execute_calls.append((query, args))
        return "UPDATE 1"


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


def test_project_repository_facade_exposes_token_control_contract():
    assert issubclass(ProjectRepository, ProjectTokenRepository)
    assert hasattr(ProjectRepository, "set_bot_token")
    assert hasattr(ProjectRepository, "set_manager_bot_token")
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
    assert args[0] is None
    assert args[1] is None
    assert repo.username_lookups == []
