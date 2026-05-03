from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.tools.builtins import (
    CRMCreateUserTool,
    CRMGetUserTool,
    EscalateTool,
    SearchKnowledgeTool,
)


@pytest.fixture
def mock_pool():
    pool = AsyncMock()
    conn = AsyncMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=None)
    pool.acquire = MagicMock(return_value=cm)
    pool.conn = conn
    return pool


@pytest.mark.asyncio
async def test_escalate_tool_uses_membership_aware_manager_targets():
    thread_repo = type("ThreadRepo", (), {"update_status": AsyncMock()})()
    queue_repo = type("QueueRepo", (), {"enqueue": AsyncMock(return_value="job-1")})()
    project_repo = type(
        "ProjectRepo",
        (),
        {"get_manager_notification_targets": AsyncMock(return_value=["111", "222"])},
    )()

    tool = EscalateTool(thread_repo, queue_repo, project_repo)

    result = await tool.run(
        {"reason": "Need a human", "priority": "high"},
        {
            "project_id": "project-1",
            "thread_id": "thread-1",
            "timestamp": "2026-04-22T14:00:00Z",
        },
    )

    assert result["ticket_created"] is True
    assert result["managers_notified"] == 2
    project_repo.get_manager_notification_targets.assert_awaited_once_with("project-1")
    queue_repo.enqueue.assert_awaited_once()


@pytest.mark.asyncio
async def test_crm_get_user_reads_project_scoped_client(mock_pool):
    client_id = uuid4()
    platform_user_id = uuid4()
    mock_pool.conn.fetchrow = AsyncMock(
        return_value={
            "id": client_id,
            "user_id": platform_user_id,
            "telegram_id": "123",
            "username": "client_username",
            "full_name": "Client Name",
            "email": "client@example.com",
            "company": "Acme",
            "phone": "+10000000000",
            "metadata": {"segment": "vip"},
        }
    )
    tool = CRMGetUserTool(mock_pool)

    result = await tool.run({"telegram_id": 123}, {"project_id": "project-1"})

    assert result["found"] is True
    assert result["user"]["id"] == str(client_id)
    assert result["user"]["user_id"] == str(platform_user_id)
    sql, project_id, telegram_id = mock_pool.conn.fetchrow.await_args.args
    assert "FROM clients" in sql
    assert "FROM users" not in sql
    assert project_id == "project-1"
    assert telegram_id == "123"


@pytest.mark.asyncio
async def test_crm_create_user_writes_project_scoped_client(mock_pool):
    client_id = uuid4()
    mock_pool.conn.fetchval = AsyncMock(side_effect=[None, client_id])
    tool = CRMCreateUserTool(mock_pool)

    result = await tool.run(
        {
            "telegram_id": 123,
            "username": "client_username",
            "first_name": "Client",
            "last_name": "Name",
            "email": "client@example.com",
            "company": "Acme",
            "phone": "+10000000000",
            "metadata": {"segment": "vip"},
        },
        {"project_id": "project-1"},
    )

    assert result == {
        "success": True,
        "client_id": str(client_id),
        "user_id": str(client_id),
    }
    lookup_sql, lookup_project_id, lookup_chat_id = (
        mock_pool.conn.fetchval.await_args_list[0].args
    )
    insert_sql = mock_pool.conn.fetchval.await_args_list[1].args[0]
    assert "FROM clients" in lookup_sql
    assert "INSERT INTO clients" in insert_sql
    assert "INSERT INTO users" not in insert_sql
    assert lookup_project_id == "project-1"
    assert lookup_chat_id == "123"


class FakeRAGService:
    def __init__(self):
        self.calls = []

    async def search_with_expansion(
        self,
        *,
        project_id,
        query,
        final_limit,
        thread_id=None,
    ):
        self.calls.append(
            {
                "project_id": project_id,
                "query": query,
                "final_limit": final_limit,
            }
        )
        return [
            {
                "id": "chunk-1",
                "content": "Knowledge answer",
                "score": 0.91,
                "method": "hybrid",
                "source": "faq.md",
                "title": "FAQ",
                "chunk_index": 2,
            }
        ]


@pytest.mark.asyncio
async def test_search_knowledge_tool_uses_injected_rag_service_without_groq():
    rag = FakeRAGService()
    tool = SearchKnowledgeTool(rag)

    result = await tool.run(
        {"query": "  pricing  ", "limit": 5},
        {"project_id": "project-1"},
    )

    assert rag.calls == [
        {
            "project_id": "project-1",
            "query": "pricing",
            "final_limit": 5,
        }
    ]
    assert result == {
        "results": [
            {
                "id": "chunk-1",
                "content": "Knowledge answer",
                "score": 0.91,
                "method": "hybrid",
                "source": "faq.md",
                "title": "FAQ",
                "chunk_index": 2,
            }
        ],
        "query": "pricing",
        "total_found": 1,
    }
