"""
LangGraph agent definition for the CRM bot.

Builds a state machine graph with nodes for load_state, rules_check, kb_search, router_llm,
tool_executor, escalate, responder, and persist. Uses the extended AgentState.
"""

from typing import Any, Dict, Optional

from langgraph.graph import StateGraph, END
from langchain_groq import ChatGroq

from src.core.config import settings
from src.core.logging import get_logger
from .state import AgentState
from .nodes.load_state import create_load_state_node
from .nodes.rules import rules_node
from .nodes.kb_search import create_kb_search_node
from .nodes.router import create_router_node
from .nodes.tool_executor import create_tool_executor_node
from .nodes.escalate import create_escalate_node
from .nodes.responder import create_responder_node
from .nodes.persist import create_persist_node
from src.core.model_registry import ModelRegistry
from src.services.rate_limit_tracker import RateLimitTracker
from src.services.model_selector import ModelSelector

logger = get_logger(__name__)


def create_agent(
    tool_registry: Optional[Any] = None,
    thread_repo=None,
    queue_repo=None,
    event_repo=None,
    project_repo=None,
    knowledge_repo=None
):
    """
    Create and compile the LangGraph agent (state machine version).

    Args:
        tool_registry: ToolRegistry instance for dynamic tool execution.
        thread_repo: ThreadRepository instance.
        queue_repo: QueueRepository instance.
        event_repo: Optional EventRepository for event sourcing.
        project_repo: Optional ProjectRepository (may be used by some nodes).
        knowledge_repo: Optional KnowledgeRepository (may be used by kb_search node,
                       but we use tool_registry for that).

    Returns:
        Compiled LangGraph workflow.
    """
    logger.info("Creating state machine agent")

    # Instantiate nodes with injected dependencies
    load_state_node = create_load_state_node(thread_repo, project_repo)
    # rules_node is a pure function, no factory needed
    kb_search_node = create_kb_search_node(tool_registry)

    # Create model selection dependencies
    registry = ModelRegistry()
    tracker = RateLimitTracker()
    selector = ModelSelector(registry, tracker)

    router_node = create_router_node(
        llm=None,
        registry=registry,
        tracker=tracker,
        selector=selector
    )  # uses default LLM from settings

    tool_executor_node = create_tool_executor_node(tool_registry)
    escalate_node = create_escalate_node(thread_repo, queue_repo)
    responder_node = create_responder_node(tool_registry)
    persist_node = create_persist_node(thread_repo, event_repo)

    # Build graph
    workflow = StateGraph(AgentState)

    # Add all nodes
    workflow.add_node("load_state", load_state_node)
    workflow.add_node("rules_check", rules_node)
    workflow.add_node("kb_search", kb_search_node)
    workflow.add_node("router_llm", router_node)
    workflow.add_node("tool_executor", tool_executor_node)
    workflow.add_node("escalate", escalate_node)
    workflow.add_node("responder", responder_node)
    workflow.add_node("persist", persist_node)

    # Set entry point
    workflow.set_entry_point("load_state")

    # Edges
    workflow.add_edge("load_state", "rules_check")

    # Conditional edges from rules_check
    def route_from_rules(state: AgentState) -> str:
        decision = state.get("decision", "PROCEED_TO_LLM")
        logger.info(f"Rules check decision: {decision}")
        return decision

    workflow.add_conditional_edges(
        "rules_check",
        route_from_rules,
        {
            "RESPOND": "responder",
            "ESCALATE": "escalate",
            "COLLECT_PROFILE": "router_llm",
            "PROCEED_TO_LLM": "kb_search",
        }
    )

    # After KB search, go to router
    workflow.add_edge("kb_search", "router_llm")

    # Conditional edges from router_llm
    def route_from_router(state: AgentState) -> str:
        decision = state.get("decision", "LLM_GENERATE")
        logger.info(f"Router decision: {decision}")
        return decision

    workflow.add_conditional_edges(
        "router_llm",
        route_from_router,
        {
            "RESPOND_KB": "responder",
            "RESPOND_TEMPLATE": "responder",
            "LLM_GENERATE": "responder",
            "CALL_TOOL": "tool_executor",
            "ESCALATE_TO_HUMAN": "escalate",
            "ESCALATE": "escalate",  # fallback for any other escalation
        }
    )

    # Edges from tool_executor
    workflow.add_conditional_edges(
        "tool_executor",
        lambda state: "responder" if not state.get("requires_human") else "escalate",
        {
            "responder": "responder",
            "escalate": "escalate",
        }
    )

    # Edges from escalate
    workflow.add_edge("escalate", "responder")

    # Edge from responder to persist
    workflow.add_edge("responder", "persist")

    # Edge from persist to END
    workflow.add_edge("persist", END)

    compiled = workflow.compile()
    logger.info("State machine agent compiled successfully")
    return compiled
