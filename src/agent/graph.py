"""
LangGraph agent definition for the CRM bot.

The runtime topology is defined by src.domain.runtime.graph_contract.
This module is only the LangGraph adapter that materializes that contract.
"""

from typing import Any, Optional

from langgraph.graph import END, StateGraph

from src.agent.nodes.escalate import create_escalate_node
from src.agent.nodes.intent_extractor import create_intent_extractor_node
from src.agent.nodes.kb_search import create_kb_search_node
from src.agent.nodes.load_state import create_load_state_node
from src.agent.nodes.persist import create_persist_node
from src.agent.nodes.policy_engine import create_policy_engine_node
from src.agent.nodes.responder import create_responder_node
from src.agent.nodes.response_generator import create_response_generator_node
from src.agent.nodes.rules import rules_node
from src.agent.nodes.tool_executor import create_tool_executor_node
from src.agent.state import AgentState
from src.domain.runtime.graph_contract import AgentGraphDecision, AgentGraphNode, AGENT_GRAPH_CONTRACT
from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)


def _require_dependency(name: str, value: Any) -> Any:
    if value is None:
        raise ValueError(f"agent graph dependency is required: {name}")
    return value


def _decision_value(decision: AgentGraphDecision) -> str:
    return decision.value


def create_agent(
    tool_registry: Optional[Any] = None,
    thread_repo=None,
    queue_repo=None,
    event_repo=None,
    project_repo=None,
    memory_repo=None,
):
    """
    Create and compile the LangGraph runtime graph.

    Required injected dependencies:
    - tool_registry
    - thread_repo
    - queue_repo

    Optional injected dependencies:
    - event_repo
    - project_repo
    - memory_repo
    """
    AGENT_GRAPH_CONTRACT.validate()
    logger.info("Creating state machine agent")

    tool_registry = _require_dependency("tool_registry", tool_registry)
    thread_repo = _require_dependency("thread_repo", thread_repo)
    queue_repo = _require_dependency("queue_repo", queue_repo)

    load_state_node = create_load_state_node(thread_repo, project_repo, memory_repo)
    kb_search_node = create_kb_search_node(tool_registry)
    intent_extractor_node = create_intent_extractor_node()
    policy_engine_node = create_policy_engine_node(event_repo=event_repo)
    response_generator_node = create_response_generator_node()
    tool_executor_node = create_tool_executor_node(tool_registry)

    ticket_create_tool = tool_registry.get_tool("ticket.create")
    if ticket_create_tool is None:
        logger.warning("TicketCreateTool not found in registry, escalation will degrade")

    escalate_node = create_escalate_node(thread_repo, queue_repo, ticket_create_tool)
    responder_node = create_responder_node(tool_registry, thread_repo=thread_repo)
    persist_node = create_persist_node(
        thread_repo=thread_repo,
        event_repo=event_repo,
        memory_repo=memory_repo,
        queue_repo=queue_repo,
    )

    graph_builder = StateGraph(AgentState)

    graph_builder.add_node(AgentGraphNode.LOAD_STATE.value, load_state_node)
    graph_builder.add_node(AgentGraphNode.RULES_CHECK.value, rules_node)
    graph_builder.add_node(AgentGraphNode.KB_SEARCH.value, kb_search_node)
    graph_builder.add_node(AgentGraphNode.INTENT_EXTRACTOR.value, intent_extractor_node)
    graph_builder.add_node(AgentGraphNode.POLICY_ENGINE.value, policy_engine_node)
    graph_builder.add_node(AgentGraphNode.TOOL_EXECUTOR.value, tool_executor_node)
    graph_builder.add_node(AgentGraphNode.ESCALATE.value, escalate_node)
    graph_builder.add_node(AgentGraphNode.RESPONSE_GENERATOR.value, response_generator_node)
    graph_builder.add_node(AgentGraphNode.RESPONDER.value, responder_node)
    graph_builder.add_node(AgentGraphNode.PERSIST.value, persist_node)

    graph_builder.set_entry_point(AGENT_GRAPH_CONTRACT.entrypoint.value)

    graph_builder.add_edge(
        AgentGraphNode.LOAD_STATE.value,
        AgentGraphNode.RULES_CHECK.value,
    )

    def route_from_rules(state: AgentState) -> str:
        decision = state.get("decision") or AgentGraphDecision.PROCEED_TO_LLM.value
        logger.info("Rules check decision: %s", decision)
        return str(decision)

    graph_builder.add_conditional_edges(
        AgentGraphNode.RULES_CHECK.value,
        route_from_rules,
        {
            _decision_value(AgentGraphDecision.RESPOND): AgentGraphNode.RESPONDER.value,
            _decision_value(AgentGraphDecision.ESCALATE): AgentGraphNode.ESCALATE.value,
            _decision_value(AgentGraphDecision.PROCEED_TO_LLM): AgentGraphNode.INTENT_EXTRACTOR.value,
        },
    )

    graph_builder.add_edge(
        AgentGraphNode.INTENT_EXTRACTOR.value,
        AgentGraphNode.POLICY_ENGINE.value,
    )

    def route_from_policy(state: AgentState) -> str:
        decision = state.get("decision") or AgentGraphDecision.LLM_GENERATE.value
        logger.info("Policy engine decision: %s", decision)
        return str(decision)

    graph_builder.add_conditional_edges(
        AgentGraphNode.POLICY_ENGINE.value,
        route_from_policy,
        {
            _decision_value(AgentGraphDecision.LLM_GENERATE): AgentGraphNode.KB_SEARCH.value,
            _decision_value(AgentGraphDecision.ESCALATE_TO_HUMAN): AgentGraphNode.ESCALATE.value,
            _decision_value(AgentGraphDecision.CALL_TOOL): AgentGraphNode.TOOL_EXECUTOR.value,
            _decision_value(AgentGraphDecision.ESCALATE): AgentGraphNode.ESCALATE.value,
        },
    )

    graph_builder.add_edge(
        AgentGraphNode.KB_SEARCH.value,
        AgentGraphNode.RESPONSE_GENERATOR.value,
    )

    graph_builder.add_conditional_edges(
        AgentGraphNode.TOOL_EXECUTOR.value,
        lambda state: (
            AgentGraphNode.RESPONSE_GENERATOR.value
            if not state.get("requires_human")
            else AgentGraphNode.ESCALATE.value
        ),
        {
            AgentGraphNode.RESPONSE_GENERATOR.value: AgentGraphNode.RESPONSE_GENERATOR.value,
            AgentGraphNode.ESCALATE.value: AgentGraphNode.ESCALATE.value,
        },
    )

    graph_builder.add_edge(
        AgentGraphNode.ESCALATE.value,
        AgentGraphNode.RESPONDER.value,
    )
    graph_builder.add_edge(
        AgentGraphNode.RESPONSE_GENERATOR.value,
        AgentGraphNode.RESPONDER.value,
    )
    graph_builder.add_edge(
        AgentGraphNode.RESPONDER.value,
        AgentGraphNode.PERSIST.value,
    )
    graph_builder.add_edge(AgentGraphNode.PERSIST.value, END)

    compiled = graph_builder.compile()
    logger.info("State machine agent compiled successfully")
    return compiled
