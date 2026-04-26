from unittest.mock import MagicMock, patch

import pytest

from src.agent.graph import create_agent
from src.domain.runtime.graph_contract import (
    AgentGraphDecision,
    AgentGraphDependency,
    AgentGraphFallback,
    AgentGraphNode,
    AgentGraphSideEffect,
    AGENT_GRAPH_CONTRACT,
)


def test_agent_graph_contract_declares_allowed_states_and_entrypoint():
    assert AGENT_GRAPH_CONTRACT.entrypoint == AgentGraphNode.LOAD_STATE
    assert AGENT_GRAPH_CONTRACT.terminal_node == AgentGraphNode.PERSIST

    assert AGENT_GRAPH_CONTRACT.nodes == (
        AgentGraphNode.LOAD_STATE,
        AgentGraphNode.RULES_CHECK,
        AgentGraphNode.INTENT_EXTRACTOR,
        AgentGraphNode.POLICY_ENGINE,
        AgentGraphNode.KB_SEARCH,
        AgentGraphNode.TOOL_EXECUTOR,
        AgentGraphNode.ESCALATE,
        AgentGraphNode.RESPONSE_GENERATOR,
        AgentGraphNode.RESPONDER,
        AgentGraphNode.PERSIST,
    )

    AGENT_GRAPH_CONTRACT.validate()


def test_agent_graph_contract_declares_transitions():
    transition_map = AGENT_GRAPH_CONTRACT.transition_map()

    assert transition_map[AgentGraphNode.LOAD_STATE][0].target == AgentGraphNode.RULES_CHECK

    rules_targets = {
        transition.decision: transition.target
        for transition in transition_map[AgentGraphNode.RULES_CHECK]
    }
    assert rules_targets[AgentGraphDecision.RESPOND] == AgentGraphNode.RESPONDER
    assert rules_targets[AgentGraphDecision.ESCALATE] == AgentGraphNode.ESCALATE
    assert rules_targets[AgentGraphDecision.PROCEED_TO_LLM] == AgentGraphNode.INTENT_EXTRACTOR

    policy_targets = {
        transition.decision: transition.target
        for transition in transition_map[AgentGraphNode.POLICY_ENGINE]
    }
    assert policy_targets[AgentGraphDecision.LLM_GENERATE] == AgentGraphNode.KB_SEARCH
    assert policy_targets[AgentGraphDecision.CALL_TOOL] == AgentGraphNode.TOOL_EXECUTOR
    assert policy_targets[AgentGraphDecision.ESCALATE_TO_HUMAN] == AgentGraphNode.ESCALATE

    terminal = transition_map[AgentGraphNode.PERSIST][0]
    assert terminal.terminal is True
    assert terminal.target is None


def test_agent_graph_contract_declares_side_effects_and_fallbacks():
    contracts = AGENT_GRAPH_CONTRACT.node_contracts

    assert AgentGraphSideEffect.LOAD_THREAD_STATE in contracts[AgentGraphNode.LOAD_STATE].side_effects
    assert AgentGraphFallback.EMPTY_USER_MEMORY in contracts[AgentGraphNode.LOAD_STATE].fallbacks

    assert AgentGraphSideEffect.SEARCH_KNOWLEDGE in contracts[AgentGraphNode.KB_SEARCH].side_effects
    assert AgentGraphFallback.EMPTY_KNOWLEDGE in contracts[AgentGraphNode.KB_SEARCH].fallbacks

    assert AgentGraphSideEffect.EXECUTE_TOOL in contracts[AgentGraphNode.TOOL_EXECUTOR].side_effects
    assert AgentGraphFallback.HUMAN_HANDOFF in contracts[AgentGraphNode.TOOL_EXECUTOR].fallbacks

    assert AgentGraphSideEffect.SEND_TELEGRAM_MESSAGE in contracts[AgentGraphNode.RESPONDER].side_effects
    assert AgentGraphFallback.DELIVERED_WITH_PERSISTENCE_DEGRADED in contracts[AgentGraphNode.RESPONDER].fallbacks

    assert AgentGraphSideEffect.SAVE_GRAPH_STATE in contracts[AgentGraphNode.PERSIST].side_effects
    assert AgentGraphSideEffect.UPDATE_ANALYTICS in contracts[AgentGraphNode.PERSIST].side_effects


def test_agent_graph_contract_declares_dependency_injection_requirements():
    contracts = AGENT_GRAPH_CONTRACT.node_contracts

    assert AgentGraphDependency.THREAD_REPOSITORY in contracts[AgentGraphNode.LOAD_STATE].required_dependencies
    assert AgentGraphDependency.TOOL_REGISTRY in contracts[AgentGraphNode.KB_SEARCH].required_dependencies
    assert AgentGraphDependency.TOOL_REGISTRY in contracts[AgentGraphNode.TOOL_EXECUTOR].required_dependencies
    assert AgentGraphDependency.QUEUE_REPOSITORY in contracts[AgentGraphNode.ESCALATE].required_dependencies
    assert AgentGraphDependency.THREAD_REPOSITORY in contracts[AgentGraphNode.PERSIST].required_dependencies


def test_create_agent_requires_core_injected_dependencies():
    with pytest.raises(ValueError, match="tool_registry"):
        create_agent()

    with pytest.raises(ValueError, match="thread_lifecycle_repo"):
        create_agent(tool_registry=MagicMock())

    with pytest.raises(ValueError, match="thread_message_repo"):
        create_agent(
            tool_registry=MagicMock(),
            thread_lifecycle_repo=MagicMock(),
        )

    with pytest.raises(ValueError, match="thread_runtime_state_repo"):
        create_agent(
            tool_registry=MagicMock(),
            thread_lifecycle_repo=MagicMock(),
            thread_message_repo=MagicMock(),
        )

    with pytest.raises(ValueError, match="thread_read_repo"):
        create_agent(
            tool_registry=MagicMock(),
            thread_lifecycle_repo=MagicMock(),
            thread_message_repo=MagicMock(),
            thread_runtime_state_repo=MagicMock(),
        )

    with pytest.raises(ValueError, match="queue_repo"):
        create_agent(
            tool_registry=MagicMock(),
            thread_lifecycle_repo=MagicMock(),
            thread_message_repo=MagicMock(),
            thread_runtime_state_repo=MagicMock(),
            thread_read_repo=MagicMock(),
        )


def test_create_agent_materializes_contract_as_langgraph_runtime():
    tool_registry = MagicMock()
    tool_registry.get_tool.return_value = MagicMock()

    with (
        patch("src.agent.graph.create_intent_extractor_node", return_value=MagicMock()),
        patch("src.agent.graph.create_response_generator_node", return_value=MagicMock()),
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

    assert hasattr(graph, "ainvoke")
    tool_registry.get_tool.assert_called_once_with("ticket.create")
