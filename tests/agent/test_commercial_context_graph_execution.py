from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from unittest.mock import MagicMock, patch

import pytest

from src.agent.graph import create_agent
from src.agent.state import AgentState


NodeFn = Callable[[AgentState], Awaitable[dict[str, object]]]


def _as_mapping(value: object) -> Mapping[str, object]:
    assert isinstance(value, Mapping)
    return value


class FakeToolRegistry:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def get_tool(self, name: str) -> object | None:
        if name == "ticket.create":
            return MagicMock()
        return None

    async def execute(
        self,
        name: str,
        args: dict[str, object],
        *,
        context: dict[str, object],
    ) -> dict[str, object]:
        self.calls.append(name)

        if name == "commercial_price_lookup":
            assert args["item_name"] == "Сколько стоит Pro?"
            assert context["project_id"] == "project-1"
            return {
                "decision": "answerable",
                "facts": [
                    {
                        "id": "fact-1",
                        "item_name": "Pro",
                        "value_kind": "exact",
                        "amount": {"amount": "2490", "currency": "RUB"},
                        "unit": "month",
                        "source_refs": [
                            {
                                "price_document_id": "price-doc-1",
                                "source_unit_id": "unit-1",
                                "quote": "Pro — 2490 ₽/мес.",
                            }
                        ],
                    }
                ],
            }

        if name == "search_knowledge":
            assert args["query"] == "Сколько стоит Pro?"
            assert context["project_id"] == "project-1"
            return {
                "query": args["query"],
                "total_found": 1,
                "results": [
                    {
                        "id": "kb-1",
                        "content": "Generic KB fallback text",
                        "score": 0.7,
                        "method": "hybrid",
                        "source": "knowledge.md",
                    }
                ],
            }

        raise AssertionError(f"unexpected tool call: {name}")


def _static_node(name: str, patch_result: dict[str, object]) -> NodeFn:
    async def node(_state: AgentState) -> dict[str, object]:
        return {"visited_" + name: True, **patch_result}

    return node


def _response_node(captured_state: dict[str, object]) -> NodeFn:
    async def node(state: AgentState) -> dict[str, object]:
        captured_state.update(dict(state))
        commercial_context = _as_mapping(state.get("commercial_context"))

        assert state["commercial_context_status"] == "answerable"
        assert commercial_context["decision"] == "answerable"
        assert state["knowledge_chunks"]
        return {"response_text": "Pro costs 2490 RUB/month."}

    return node


@pytest.mark.asyncio
async def test_graph_executes_commercial_context_lookup_before_kb_search() -> None:
    tool_registry = FakeToolRegistry()
    captured_response_state: dict[str, object] = {}

    with (
        patch(
            "src.agent.graph.create_load_state_node",
            return_value=_static_node("load_state", {}),
        ),
        patch(
            "src.agent.graph.rules_node",
            _static_node("rules", {"decision": "PROCEED_TO_LLM"}),
        ),
        patch(
            "src.agent.graph.create_intent_extractor_node",
            return_value=_static_node("intent", {}),
        ),
        patch(
            "src.agent.graph.create_policy_engine_node",
            return_value=_static_node("policy", {"decision": "LLM_GENERATE"}),
        ),
        patch(
            "src.agent.graph.create_response_generator_node",
            return_value=_response_node(captured_response_state),
        ),
        patch(
            "src.agent.graph.create_responder_node",
            return_value=_static_node("responder", {"delivered": True}),
        ),
        patch(
            "src.agent.graph.create_persist_node",
            return_value=_static_node("persist", {}),
        ),
        patch(
            "src.agent.graph.create_escalate_node",
            return_value=_static_node("escalate", {"requires_human": True}),
        ),
        patch(
            "src.agent.graph.create_tool_executor_node",
            return_value=_static_node("tool_executor", {}),
        ),
        patch(
            "src.agent.graph.template_response_node",
            _static_node("template_response", {"response_text": "template"}),
        ),
    ):
        graph = create_agent(
            tool_registry=tool_registry,
            thread_lifecycle_repo=MagicMock(),
            thread_message_repo=MagicMock(),
            thread_runtime_state_repo=MagicMock(),
            thread_read_repo=MagicMock(),
            queue_repo=MagicMock(),
            event_repo=MagicMock(),
            project_repo=MagicMock(),
            memory_repo=MagicMock(),
        )

        result = await graph.ainvoke(
            {
                "project_id": "project-1",
                "thread_id": "thread-1",
                "user_input": "Сколько стоит Pro?",
            }
        )

    assert tool_registry.calls == ["commercial_price_lookup", "search_knowledge"]
    assert result["response_text"] == "Pro costs 2490 RUB/month."
    captured_commercial_context = _as_mapping(
        captured_response_state.get("commercial_context")
    )

    assert captured_response_state["commercial_context_status"] == "answerable"
    assert captured_commercial_context["decision"] == "answerable"
    assert captured_response_state["knowledge_chunks"]
