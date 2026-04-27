import json
from uuid import uuid4

import pytest

from src.infrastructure.db.repositories.project.project_channels import (
    ProjectChannelRepository,
)


class FakeConnection:
    def __init__(self):
        self.query = None
        self.args = None

    async def fetchrow(self, query, *args):
        self.query = query
        self.args = args
        return {
            "id": str(uuid4()),
            "project_id": str(args[0]),
            "kind": args[1],
            "provider": args[2],
            "status": args[3],
            "config_json": args[4],
            "created_at": None,
            "updated_at": None,
        }


class FakeAcquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakePool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        return FakeAcquire(self.conn)


@pytest.mark.asyncio
async def test_upsert_project_channel_serializes_config_json_for_asyncpg():
    conn = FakeConnection()
    repo = ProjectChannelRepository(FakePool(conn))

    await repo.upsert_project_channel(
        project_id=str(uuid4()),
        kind="manager",
        provider="telegram",
        status="active",
        config_json={"token_configured": True},
    )

    assert conn.args is not None
    config_json_arg = conn.args[4]
    assert isinstance(config_json_arg, str)
    assert json.loads(config_json_arg) == {"token_configured": True}
