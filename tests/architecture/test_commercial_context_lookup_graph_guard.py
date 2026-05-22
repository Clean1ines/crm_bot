from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GRAPH = ROOT / "src/agent/graph.py"
GRAPH_CONTRACT = ROOT / "src/domain/runtime/graph_contract.py"
NODE = ROOT / "src/agent/nodes/commercial_context_lookup.py"
KB_SEARCH = ROOT / "src/agent/nodes/kb_search.py"


def test_commercial_context_lookup_node_is_between_policy_and_kb_search() -> None:
    graph_source = GRAPH.read_text(encoding="utf-8")
    contract_source = GRAPH_CONTRACT.read_text(encoding="utf-8")

    assert "AgentGraphNode.COMMERCIAL_CONTEXT_LOOKUP" in graph_source
    assert "AgentGraphNode.COMMERCIAL_CONTEXT_LOOKUP" in contract_source
    assert "AgentGraphDecision.LLM_GENERATE" in contract_source
    assert "AgentGraphNode.COMMERCIAL_CONTEXT_LOOKUP.value" in graph_source
    assert (
        "AgentGraphNode.COMMERCIAL_CONTEXT_LOOKUP.value,\n"
        "        AgentGraphNode.KB_SEARCH.value" in graph_source
    )


def test_commercial_context_lookup_uses_structured_price_tool_without_kb_search() -> (
    None
):
    node_source = NODE.read_text(encoding="utf-8")
    kb_source = KB_SEARCH.read_text(encoding="utf-8")

    assert '"commercial_price_lookup"' in node_source
    assert '"search_knowledge"' not in node_source
    assert '"commercial_price_lookup"' not in kb_source


def test_commercial_context_lookup_does_not_generate_or_send_responses() -> None:
    node_source = NODE.read_text(encoding="utf-8")

    assert "response_text" not in node_source
    assert "TelegramSendMessageTool" not in node_source
    assert "create_responder_node" not in node_source
