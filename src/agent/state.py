"""
Agent state definition for the LangGraph runtime.

Defines the TypedDict structure that carries conversation state
through the agent graph, including messages, context, and flags.
"""

from typing import Annotated, Sequence, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from src.domain.runtime.dialog_state import DialogState
from src.domain.runtime.state_contracts import (
    ClientProfileState,
    HistoryMessage,
    KnowledgeChunkState,
    ProjectRuntimeConfigurationState,
    ToolArguments,
    ToolCallRecord,
)

class AgentState(TypedDict):
    """
    State container for the LangGraph agent runtime.
    
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
        project_configuration: Explicit project settings/policies/integrations/limits.
        
        # Analytics fields
        intent: str | None  # Detected intent (e.g., "pricing", "support", "sales")
        cta: str | None     # Call-to-action type (e.g., "call_manager")
        lifecycle: str | None  # Customer lifecycle stage (e.g., "cold", "warm", "hot")
        features: Dict | None  # Tracked feature interest (e.g., {"auto_reply": True})
        
        # Runtime dialog state fields (loaded from user memory)
        dialog_state: DialogState | None  # Current dialog state snapshot
        topic: str | None                 # Current conversation topic
        lead_status: str | None           # Lead status (e.g., "new", "qualified", "lost")
        repeat_count: int | None          # Number of times user repeated a question
    """
    # Core fields (existing)
    messages: Annotated[Sequence[BaseMessage], add_messages]
    project_id: str
    thread_id: str
    escalation_requested: bool
    tool_calls: list[ToolCallRecord] | None

    # New pipeline fields (all optional for backward compatibility)
    user_input: str | None
    client_profile: ClientProfileState | None
    conversation_summary: str | None
    history: list[HistoryMessage] | None
    knowledge_chunks: list[KnowledgeChunkState] | None
    decision: str | None  # e.g., "RESPOND", "TOOL", "ESCALATE", "COLLECT"
    tool_name: str | None
    tool_args: ToolArguments | None
    tool_result: object | None
    user_memory: dict[str, object] | None # Added hidden field discovered during audit
    response_text: str | None
    requires_human: bool
    confidence: float | None
    chat_id: int | None  # Telegram chat ID of the user, needed for responder
    message_sent: bool | None  # Flag indicating that the message was already sent by the graph
    trace_id: str | None  # Unique trace identifier for observability
    client_id: str | None  # UUID of the client for memory storage
    project_configuration: ProjectRuntimeConfigurationState | None  # Explicit project personalization config
    close_ticket: bool | None # Added hidden field discovered during audit

    # Analytics fields
    intent: str | None  # Detected intent (e.g., "pricing", "support", "sales")
    cta: str | None     # Call-to-action type (e.g., "call_manager")
    lifecycle: str | None  # Customer lifecycle stage (e.g., "cold", "warm", "hot")
    features: dict[str, object] | None  # Tracked feature interest (e.g., {"auto_reply": True})
    
    # Runtime dialog state fields (loaded from user memory)
    dialog_state: DialogState | None  # Current dialog state snapshot
    topic: str | None         # Current conversation topic
    lead_status: str | None   # Lead status (e.g., "new", "qualified", "lost")
    repeat_count: int | None  # Number of times user repeated a question
