import httpx
import pytest

from src.domain.runtime.tool_execution import ToolExecutionStatus
from src.tools.http_tool import HTTPTool


@pytest.mark.asyncio
async def test_http_tool_completed_request_returns_explicit_success(monkeypatch):
    class FakeResponse:
        status_code = 404
        headers = {"content-type": "application/json"}

        def json(self):
            return {"message": "not found"}

    class FakeClient:
        def __init__(self, *, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def request(self, *_args, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr("src.tools.http_tool.httpx.AsyncClient", FakeClient)
    tool = HTTPTool()

    result = await tool.run(
        {"method": "GET", "url": "https://api.example.com/items"},
        {"project_id": "project-1"},
    )

    assert result.status is ToolExecutionStatus.SUCCEEDED
    assert isinstance(result.payload, dict)
    assert result.payload["status_code"] == 404
    assert result.payload["body"] == {"message": "not found"}


@pytest.mark.asyncio
async def test_http_tool_transport_exception_propagates_for_executor_policy(
    monkeypatch,
):
    class FakeClient:
        def __init__(self, *, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def request(self, *_args, **_kwargs):
            raise httpx.ConnectError("network down")

    monkeypatch.setattr("src.tools.http_tool.httpx.AsyncClient", FakeClient)
    tool = HTTPTool()

    with pytest.raises(Exception):
        await tool.run(
            {"method": "GET", "url": "https://api.example.com/items"},
            {"project_id": "project-1"},
        )
