from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.infrastructure.db.repositories.client_repository import ClientRepository


class MockAcquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.fixture
def mock_conn():
    conn = AsyncMock()
    conn.fetch = AsyncMock()
    conn.fetchrow = AsyncMock()
    return conn


@pytest.fixture
def mock_pool(mock_conn):
    pool = MagicMock()
    pool.acquire.return_value = MockAcquire(mock_conn)
    return pool


@pytest.fixture
def client_repo(mock_pool):
    return ClientRepository(mock_pool)


@pytest.mark.asyncio
async def test_list_for_project_returns_clients_and_stats(client_repo, mock_conn):
    project_id = uuid4()
    client_id = uuid4()
    user_id = uuid4()
    latest_thread_id = uuid4()

    mock_conn.fetch.return_value = [
        {
            "id": client_id,
            "user_id": user_id,
            "username": "client",
            "full_name": "Client User",
            "email": "client@example.com",
            "company": "Acme",
            "phone": "+10000000000",
            "metadata": {"segment": "vip"},
            "chat_id": 12345,
            "source": "telegram",
            "created_at": "2025-01-01T00:00:00",
            "last_activity_at": "2025-01-02T00:00:00",
            "threads_count": 2,
            "latest_thread_id": latest_thread_id,
        }
    ]
    mock_conn.fetchrow.return_value = {
        "total_clients": 5,
        "new_clients_7d": 2,
        "active_dialogs": 1,
    }

    result = await client_repo.list_for_project_view(
        str(project_id),
        limit=10,
        offset=5,
        search="cli",
    )

    assert len(result.clients) == 1
    client = result.clients[0]

    assert client.id == str(client_id)
    assert client.user_id == str(user_id)
    assert client.email == "client@example.com"
    assert client.company == "Acme"
    assert client.metadata == {"segment": "vip"}
    assert client.latest_thread_id == str(latest_thread_id)
    assert client.threads_count == 2

    assert result.total_clients == 1
    assert result.new_clients_7d == 1
    assert result.active_dialogs == 1


@pytest.mark.asyncio
async def test_get_by_id_returns_project_scoped_client(client_repo, mock_conn):
    project_id = uuid4()
    client_id = uuid4()
    user_id = uuid4()

    mock_conn.fetchrow.return_value = {
        "id": client_id,
        "user_id": user_id,
        "username": "client",
        "full_name": "Client User",
        "email": "client@example.com",
        "company": "Acme",
        "phone": "+10000000000",
        "metadata": {"segment": "vip"},
        "chat_id": 12345,
        "source": "telegram",
        "created_at": "2025-01-01T00:00:00",
    }

    result = await client_repo.get_by_id_view(str(project_id), str(client_id))

    assert result is not None
    assert result.id == str(client_id)
    assert result.user_id == str(user_id)
    assert result.email == "client@example.com"
    assert result.company == "Acme"
    assert result.metadata == {"segment": "vip"}


@pytest.mark.asyncio
async def test_get_by_id_returns_none_when_missing(client_repo, mock_conn):
    mock_conn.fetchrow.return_value = None

    result = await client_repo.get_by_id_view(str(uuid4()), str(uuid4()))

    assert result is None
