"""
LangGraph agent definition for the CRM bot.

Builds a state graph with agent and tool nodes.
Supports both legacy direct tool calls and ToolRegistry-based dynamic execution.
"""

from typing import Any, Dict, Optional

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_groq import ChatGroq

from src.core.config import settings
from src.core.logging import get_logger
from .state import AgentState
from . import tools  # импортируем модуль целиком для установки контекста

logger = get_logger(__name__)


def create_agent(tool_registry: Optional[Any] = None):
    """
    Create and compile the LangGraph agent.
    
    Args:
        tool_registry: Optional ToolRegistry instance for dynamic tool resolution.
                      If None, uses legacy direct tool calls.
    
    Returns:
        Compiled LangGraph workflow.
    """
    model_name = getattr(settings, 'GROQ_MODEL', 'llama-3.3-70b-versatile')
    logger.info("Creating agent", extra={"model": model_name})

    model = ChatGroq(
        model="llama-3.1-8b-instant",
        temperature=0.6,
        api_key=settings.GROQ_API_KEY,
    )

    # Determine which tools to use based on registry availability
    if tool_registry is not None:
        # Use registry-based tools for dynamic execution
        logger.debug("Using ToolRegistry for dynamic tool resolution")
        tool_list = [
            tools.search_knowledge_base,
            tools.escalate_to_manager,
        ]
        # Note: In future, tools from registry can be dynamically added here
    else:
        # Use legacy direct tool calls
        logger.debug("Using legacy direct tool calls")
        tool_list = [
            tools.search_knowledge_base,
            tools.escalate_to_manager,
        ]

    model_with_tools = model.bind_tools(tool_list)

    async def call_model(state: AgentState) -> Dict[str, Any]:
        """
        Call the LLM model with current state and handle tool calls.
        
        Args:
            state: Current AgentState with messages and context.
        
        Returns:
            Dict with updated messages and optional escalation flag.
        """
        logger.debug(
            "Agent invoked",
            extra={
                "project_id": state.get("project_id"),
                "thread_id": state.get("thread_id"),
                "message_count": len(state["messages"])
            }
        )
        
        # Устанавливаем контекст для инструментов перед вызовом (legacy support)
        tools.set_current_context(state["project_id"], state["thread_id"])
        
        response = await model_with_tools.ainvoke(state["messages"])

        escalation = False
        if hasattr(response, "tool_calls") and response.tool_calls:
            for tc in response.tool_calls:
                if tc.get("name") == "escalate_to_manager":
                    escalation = True
                    logger.info(
                        "Escalation detected in tool call",
                        extra={
                            "project_id": state.get("project_id"),
                            "thread_id": state.get("thread_id")
                        }
                    )
                    break
        
        result: Dict[str, Any] = {"messages": [response]}
        if escalation:
            result["escalation_requested"] = True
            
        return result

    workflow = StateGraph(AgentState)
    workflow.add_node("agent", call_model)
    workflow.add_node("tools", ToolNode(tool_list))
    workflow.set_entry_point("agent")

    def should_continue(state: AgentState) -> str:
        """
        Determine next node based on last message.
        
        Args:
            state: Current AgentState.
        
        Returns:
            "tools" if tool calls pending, else END.
        """
        last_message = state["messages"][-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            return "tools"
        return END

    workflow.add_conditional_edges("agent", should_continue)
    workflow.add_edge("tools", "agent")

    compiled = workflow.compile()
    logger.info("Agent compiled successfully")
    return compiled
