"""
Agent state definition for LangGraph workflow.

Defines the TypedDict structure that carries conversation state
through the agent graph, including messages, context, and flags.
"""

from typing import Annotated, Sequence, List, Dict, Any, Optional, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class DialogState(TypedDict):
    """
    Structure for tracking dialog context across turns.
    """
    last_intent: Optional[str]
    last_cta: Optional[str]
    last_topic: Optional[str]
    repeat_count: int
    lead_status: str
    lifecycle: str

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
        
        # New fields for enhanced pipeline
        user_input: The original user message text.
        client_profile: Dictionary containing client CRM data (from users table).
        conversation_summary: Condensed summary of conversation history.
        history: List of recent messages (as dicts) for context.
        knowledge_chunks: Results from knowledge base search (list of chunks with scores).
        decision: Decision made by router ("RESPOND", "TOOL", "ESCALATE", "COLLECT").
        tool_name: Name of the tool to execute (if decision is TOOL).
        tool_args: Arguments for the tool.
        tool_result: Result returned by tool execution.
        response_text: Final text response to send to user.
        requires_human: Whether human intervention is needed.
        confidence: Confidence score of the decision (0-1).
        trace_id: Unique identifier for tracing the entire graph execution.
        client_id: UUID of the client (string format) for user memory.
        
        # Analytics fields
        intent: Optional[str]  # Detected intent (e.g., "pricing", "support", "sales")
        cta: Optional[str]     # Call-to-action type (e.g., "request_demo", "call_manager")
        lifecycle: Optional[str]  # Customer lifecycle stage (e.g., "cold", "warm", "hot")
        features: Optional[Dict]  # Tracked feature interest (e.g., {"auto_reply": True})
        
        # Runtime dialog state fields (loaded from user memory)
        dialog_state: Optional[DialogState]  # Current dialog state snapshot
        topic: Optional[str]                 # Current conversation topic
        lead_status: Optional[str]           # Lead status (e.g., "new", "qualified", "lost")
        repeat_count: Optional[int]          # Number of times user repeated a question
    """
    # Core fields (existing)
    messages: Annotated[Sequence[BaseMessage], add_messages]
    project_id: str
    thread_id: str
    escalation_requested: bool
    tool_calls: Optional[List[Dict[str, Any]]]

    # New pipeline fields (all optional for backward compatibility)
    user_input: Optional[str]
    client_profile: Optional[Dict[str, Any]]
    conversation_summary: Optional[str]
    history: Optional[List[Dict[str, Any]]]
    knowledge_chunks: Optional[List[Dict[str, Any]]]
    decision: Optional[str]  # e.g., "RESPOND", "TOOL", "ESCALATE", "COLLECT"
    tool_name: Optional[str]
    tool_args: Optional[Dict[str, Any]]
    tool_result: Optional[Any]
    user_memory: Optional[Dict[str, Any]] # Added hidden field discovered during audit
    response_text: Optional[str]
    requires_human: bool
    confidence: Optional[float]
    chat_id: Optional[int]  # Telegram chat ID of the user, needed for responder
    message_sent: Optional[bool]  # Flag indicating that the message was already sent by the graph
    trace_id: Optional[str]  # Unique trace identifier for observability
    client_id: Optional[str]  # UUID of the client for memory storage
    close_ticket: Optional[bool] # Added hidden field discovered during audit

    # Analytics fields
    intent: Optional[str]  # Detected intent (e.g., "pricing", "support", "sales")
    cta: Optional[str]     # Call-to-action type (e.g., "request_demo", "call_manager")
    lifecycle: Optional[str]  # Customer lifecycle stage (e.g., "cold", "warm", "hot")
    features: Optional[Dict]  # Tracked feature interest (e.g., {"auto_reply": True})
    
    # Runtime dialog state fields (loaded from user memory)
    dialog_state: Optional[DialogState]  # Current dialog state snapshot
    topic: Optional[str]         # Current conversation topic
    lead_status: Optional[str]   # Lead status (e.g., "new", "qualified", "lost")
    repeat_count: Optional[int]  # Number of times user repeated a question
