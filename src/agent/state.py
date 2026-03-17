"""
Agent state definition for LangGraph workflow.

Defines the TypedDict structure that carries conversation state
through the agent graph, including messages, context, and flags.
"""

from typing import Annotated, Sequence, List, Dict, Any, Optional, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    """
    State container for the LangGraph agent workflow.
    
    This TypedDict defines all fields that flow through the agent graph,
    enabling state persistence, event reconstruction, and tool execution tracking.
    
    Fields:
        messages: Annotated list of BaseMessage objects. The add_messages
                  reducer ensures new messages are appended, not replaced.
        project_id: UUID of the project (string format) for multi-tenant isolation.
        thread_id: UUID of the conversation thread (string format) for event streaming.
        escalation_requested: Boolean flag indicating if human escalation is needed.
        tool_calls: Optional list of tool call records for audit and replay.
    """
    # add_messages means new messages are appended to the list, not replacing it
    messages: Annotated[Sequence[BaseMessage], add_messages]
    project_id: str
    thread_id: str
    # Flag indicating the agent decided to escalate the conversation to a manager
    escalation_requested: bool
    # Optional list of tool call records for event-sourced replay and debugging
    tool_calls: Optional[List[Dict[str, Any]]]
