"""
LangGraph agent definition for the CRM bot.

Builds a state machine graph with nodes for load_state, rules_check, kb_search,
intent_extractor, policy_engine, tool_executor, escalate, response_generator,
responder, and persist. Uses the extended AgentState.
"""

from typing import Any, Dict, Optional

from langgraph.graph import StateGraph, END

from src.infrastructure.config.settings import settings
from src.infrastructure.logging.logger import get_logger
from .state import AgentState
from .nodes.load_state import create_load_state_node
from .nodes.rules import rules_node
from .nodes.kb_search import create_kb_search_node
from .nodes.intent_extractor import create_intent_extractor_node
from .nodes.policy_engine import create_policy_engine_node
from .nodes.response_generator import create_response_generator_node
from .nodes.tool_executor import create_tool_executor_node
from .nodes.escalate import create_escalate_node
from .nodes.responder import create_responder_node
from .nodes.persist import create_persist_node
from src.tools.builtins import TicketCreateTool

logger = get_logger(__name__)


def create_agent(
    tool_registry: Optional[Any] = None,
    thread_repo=None,
    queue_repo=None,
    event_repo=None,
    project_repo=None,
    memory_repo=None
):
    """
    Create and compile the LangGraph agent (state machine version).

    Args:
        tool_registry: ToolRegistry instance for dynamic tool execution.
        thread_repo: ThreadRepository instance.
        queue_repo: QueueRepository instance.
        event_repo: Optional EventRepository for event sourcing.
        project_repo: Optional ProjectRepository (may be used by some nodes).
        project_repo: Optional ProjectRepository (may be used by some nodes).
        memory_repo: Optional MemoryRepository for long-term memory.

    Returns:
        Compiled LangGraph runtime graph.
    """
    logger.info("Creating state machine agent")

    # Instantiate nodes with injected dependencies
    load_state_node = create_load_state_node(thread_repo, project_repo, memory_repo)
    # rules_node is a pure function, no factory needed
    kb_search_node = create_kb_search_node(tool_registry)
    intent_extractor_node = create_intent_extractor_node()  # uses lightweight LLM
    policy_engine_node = create_policy_engine_node()
    response_generator_node = create_response_generator_node()  # uses main LLM
    tool_executor_node = create_tool_executor_node(tool_registry)

    # Get TicketCreateTool from registry (or create if not found)
    ticket_create_tool = tool_registry.get_tool("ticket.create")
    if ticket_create_tool is None:
        logger.warning("TicketCreateTool not found in registry, escalation will not create ticket")

    escalate_node = create_escalate_node(thread_repo, queue_repo, ticket_create_tool)
    # Pass thread_repo to responder node so it can save assistant messages
    responder_node = create_responder_node(tool_registry, thread_repo=thread_repo)
    persist_node = create_persist_node(thread_repo, event_repo, memory_repo)

    # Build graph
    graph_builder = StateGraph(AgentState)

    # Add all nodes
    graph_builder.add_node("load_state", load_state_node)
    graph_builder.add_node("rules_check", rules_node)
    graph_builder.add_node("kb_search", kb_search_node)
    graph_builder.add_node("intent_extractor", intent_extractor_node)
    graph_builder.add_node("policy_engine", policy_engine_node)
    graph_builder.add_node("tool_executor", tool_executor_node)
    graph_builder.add_node("escalate", escalate_node)
    graph_builder.add_node("response_generator", response_generator_node)
    graph_builder.add_node("responder", responder_node)
    graph_builder.add_node("persist", persist_node)

    # Set entry point
    graph_builder.set_entry_point("load_state")

    # Edges
    graph_builder.add_edge("load_state", "rules_check")

    # Conditional edges from rules_check
    def route_from_rules(state: AgentState) -> str:
        decision = state.get("decision", "PROCEED_TO_LLM")
        logger.info(f"Rules check decision: {decision}")
        return decision

    graph_builder.add_conditional_edges(
        "rules_check",
        route_from_rules,
        {
            "RESPOND": "responder",            # fallback if rules returned RESPOND (though rules now only PROCEED or ESCALATE)
            "ESCALATE": "escalate",
            "PROCEED_TO_LLM": "intent_extractor",  # <-- Changed: go directly to intent_extractor
        }
    )

    # Intent extraction then policy engine (no kb_search before)
    graph_builder.add_edge("intent_extractor", "policy_engine")

    # Conditional edges from policy_engine
    def route_from_policy(state: AgentState) -> str:
        decision = state.get("decision", "LLM_GENERATE")
        logger.info(f"Policy engine decision: {decision}")
        return decision

    graph_builder.add_conditional_edges(
        "policy_engine",
        route_from_policy,
        {
            "LLM_GENERATE": "kb_search",        # <-- Changed: go to kb_search first
            "ESCALATE_TO_HUMAN": "escalate",
            "CALL_TOOL": "tool_executor",
            "ESCALATE": "escalate",  # fallback
        }
    )

    # After kb_search, generate response
    graph_builder.add_edge("kb_search", "response_generator")

    # Edges from tool_executor
    graph_builder.add_conditional_edges(
        "tool_executor",
        lambda state: "response_generator" if not state.get("requires_human") else "escalate",
        {
            "response_generator": "response_generator",
            "escalate": "escalate",
        }
    )

    # Edges from escalate
    graph_builder.add_edge("escalate", "responder")

    # After response generation, go to responder
    graph_builder.add_edge("response_generator", "responder")

    # Edge from responder to persist
    graph_builder.add_edge("responder", "persist")

    # Edge from persist to END
    graph_builder.add_edge("persist", END)

    compiled = graph_builder.compile()
    logger.info("State machine agent compiled successfully")
    return compiled
