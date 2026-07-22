from src.domain.runtime.graph_contract import (
    AGENT_GRAPH_CONTRACT,
    AgentGraphNode,
    AgentGraphRoute,
)


def test_policy_generation_routes_are_distinct_in_graph_contract():
    routes = {
        transition.route: transition.target
        for transition in AGENT_GRAPH_CONTRACT.transitions
        if transition.source is AgentGraphNode.POLICY_ENGINE
        and transition.route is not None
    }

    assert routes[AgentGraphRoute.LLM_GENERATE_KNOWLEDGE] is AgentGraphNode.KB_SEARCH
    assert (
        routes[AgentGraphRoute.LLM_GENERATE_CONVERSATIONAL]
        is AgentGraphNode.RESPONSE_GENERATOR
    )
    assert (
        routes[AgentGraphRoute.LLM_GENERATE_INVALID_MODE]
        is AgentGraphNode.RESPONSE_GENERATOR
    )
