from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.tools.builtins import (
    CRMCollectProfileTool,
    CRMCreateUserTool,
    CRMGetUserTool,
    TelegramSendMessageTool,
    EscalateTool,
    SearchKnowledgeTool,
    TicketCreateTool,
)
from src.domain.runtime.tool_execution import ToolExecutionStatus


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

    assert result.status is ToolExecutionStatus.SUCCEEDED
    assert isinstance(result.payload, dict)
    assert result.payload["ticket_created"] is True
    assert result.payload["managers_notified"] == 2
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

    assert result.status is ToolExecutionStatus.SUCCEEDED
    assert isinstance(result.payload, dict)
    assert result.payload["found"] is True
    user = result.payload["user"]
    assert isinstance(user, dict)
    assert user["id"] == str(client_id)
    assert user["user_id"] == str(platform_user_id)
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

    assert result.status is ToolExecutionStatus.SUCCEEDED
    assert result.payload == {
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
    assert result.status is ToolExecutionStatus.SUCCEEDED
    assert result.payload == {
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


@pytest.mark.asyncio
async def test_search_knowledge_tool_empty_query_returns_business_failure():
    rag = FakeRAGService()
    tool = SearchKnowledgeTool(rag)

    result = await tool.run({"query": "   "}, {"project_id": "project-1"})

    assert result.status is ToolExecutionStatus.FAILED
    assert result.safe_error_code == "tool_business_rejected"
    assert rag.calls == []


@pytest.mark.asyncio
async def test_search_knowledge_tool_technical_exception_propagates_for_executor_policy():
    class FailingRAGService:
        async def search_with_expansion(self, **_kwargs):
            raise RuntimeError("rag down")

    tool = SearchKnowledgeTool(FailingRAGService())

    with pytest.raises(Exception):
        await tool.run({"query": "pricing"}, {"project_id": "project-1"})


@pytest.mark.asyncio
async def test_crm_collect_profile_tool_returns_explicit_success():
    tool = CRMCollectProfileTool()

    result = await tool.run({}, {"project_id": "project-1"})

    assert result.status is ToolExecutionStatus.SUCCEEDED
    assert isinstance(result.payload, dict)
    assert result.payload["asking_fields"]


@pytest.mark.asyncio
async def test_ticket_create_tool_returns_explicit_success(mock_pool):
    ticket_id = uuid4()
    mock_pool.conn.fetchval = AsyncMock(return_value=ticket_id)
    tool = TicketCreateTool(mock_pool)

    result = await tool.run(
        {"title": "Help", "description": "Details"},
        {"project_id": "project-1", "thread_id": "thread-1", "user_id": "user-1"},
    )

    assert result.status is ToolExecutionStatus.SUCCEEDED
    assert result.payload == {"ticket_id": str(ticket_id), "status": "open"}


@pytest.mark.asyncio
async def test_ticket_create_tool_technical_exception_propagates_for_executor_policy(
    mock_pool,
):
    mock_pool.conn.fetchval = AsyncMock(side_effect=RuntimeError("db down"))
    tool = TicketCreateTool(mock_pool)

    with pytest.raises(RuntimeError):
        await tool.run({"title": "Help"}, {"project_id": "project-1"})


@pytest.mark.asyncio
async def test_crm_create_user_existing_contact_is_business_failure(mock_pool):
    client_id = uuid4()
    mock_pool.conn.fetchval = AsyncMock(return_value=client_id)
    tool = CRMCreateUserTool(mock_pool)

    result = await tool.run({"telegram_id": 123}, {"project_id": "project-1"})

    assert result.status is ToolExecutionStatus.FAILED
    assert result.safe_error_code == "tool_business_rejected"
    assert isinstance(result.payload, dict)
    assert result.payload["reason"] == "contact_already_exists"


class FakeTokenRepo:
    def __init__(self, token="token"):
        self.token = token

    async def get_bot_token(self, _project_id):
        return self.token


@pytest.mark.asyncio
async def test_telegram_send_message_ok_true_returns_success(monkeypatch):
    class FakeResponse:
        status_code = 200

        def json(self):
            return {"ok": True, "result": {"message_id": 42}}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, *_args, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr("src.tools.builtins.httpx.AsyncClient", lambda: FakeClient())
    tool = TelegramSendMessageTool(FakeTokenRepo())

    result = await tool.run(
        {"chat_id": 1, "text": "hello"}, {"project_id": "project-1"}
    )

    assert result.status is ToolExecutionStatus.SUCCEEDED
    assert result.payload == {"ok": True, "message_id": 42}


@pytest.mark.asyncio
async def test_telegram_send_message_ok_false_returns_failed(monkeypatch):
    class FakeResponse:
        status_code = 200

        def json(self):
            return {"ok": False, "description": "rejected"}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, *_args, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr("src.tools.builtins.httpx.AsyncClient", lambda: FakeClient())
    tool = TelegramSendMessageTool(FakeTokenRepo())

    result = await tool.run(
        {"chat_id": 1, "text": "hello"}, {"project_id": "project-1"}
    )

    assert result.status is ToolExecutionStatus.FAILED
    assert result.safe_error_code == "telegram_request_rejected"


@pytest.mark.asyncio
async def test_telegram_send_message_exception_propagates_for_executor_policy(
    monkeypatch,
):
    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, *_args, **_kwargs):
            raise RuntimeError("network down")

    monkeypatch.setattr("src.tools.builtins.httpx.AsyncClient", lambda: FakeClient())
    tool = TelegramSendMessageTool(FakeTokenRepo())

    with pytest.raises(RuntimeError):
        await tool.run({"chat_id": 1, "text": "hello"}, {"project_id": "project-1"})
