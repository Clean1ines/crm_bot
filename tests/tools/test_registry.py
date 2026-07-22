import pytest

from src.domain.runtime.tool_execution import ToolExecutionOutcome, ToolExecutionStatus
from src.tools.registry import Tool, ToolRegistry


class RawTool(Tool):
    name = "raw"
    description = "Raw test tool"
    input_schema = {"type": "object", "additionalProperties": True}

    def __init__(self, value):
        self.value = value

    async def run(self, args, context):  # intentionally invalid contract
        return self.value


class OutcomeTool(Tool):
    name = "outcome"
    description = "Outcome test tool"
    input_schema = {"type": "object", "additionalProperties": True}

    def __init__(self, outcome):
        self.outcome = outcome

    async def run(self, args, context):
        return self.outcome


@pytest.mark.asyncio
@pytest.mark.parametrize("value", [{"value": 1}, [1], "value"])
async def test_registry_rejects_raw_tool_returns(value):
    registry = ToolRegistry()
    registry.register(RawTool(value))

    result = await registry.execute("raw", {}, {"project_id": "project-1"})

    assert result.status is ToolExecutionStatus.FAILED
    assert result.safe_error_code == "invalid_tool_outcome"
    assert result.payload is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"value": 1},
        [1],
        "value",
        {"ok": False, "value": "business data"},
        {"error": "business validation message"},
    ],
)
async def test_registry_accepts_explicit_success_payloads(payload):
    registry = ToolRegistry()
    registry.register(OutcomeTool(ToolExecutionOutcome.succeeded(payload=payload)))

    result = await registry.execute("outcome", {}, {"project_id": "project-1"})

    assert result.status is ToolExecutionStatus.SUCCEEDED
    assert result.payload == payload


@pytest.mark.asyncio
async def test_registry_accepts_explicit_success_without_payload_with_response_text():
    registry = ToolRegistry()
    registry.register(
        OutcomeTool(ToolExecutionOutcome.succeeded(response_text="Done."))
    )

    result = await registry.execute("outcome", {}, {"project_id": "project-1"})

    assert result.status is ToolExecutionStatus.SUCCEEDED
    assert result.payload is None
    assert result.response_text == "Done."


@pytest.mark.asyncio
async def test_registry_failed_outcome_remains_failed_with_payload():
    registry = ToolRegistry()
    registry.register(
        OutcomeTool(
            ToolExecutionOutcome.failed(
                safe_error_code="tool_business_rejected",
                payload={"ok": True},
            )
        )
    )

    result = await registry.execute("outcome", {}, {"project_id": "project-1"})

    assert result.status is ToolExecutionStatus.FAILED
    assert result.safe_error_code == "tool_business_rejected"
    assert result.payload == {"ok": True}
