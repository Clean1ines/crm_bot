"""
LangGraph agent definition for the CRM bot.
Builds a state graph with agent and tool nodes.
"""

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_groq import ChatGroq
from src.core.config import settings
from src.core.logging import get_logger
from .state import AgentState
from . import tools  # импортируем модуль целиком для установки контекста

logger = get_logger(__name__)

def create_agent():
    """Create and compile the LangGraph agent."""
    logger.info(f"Creating agent with model {getattr(settings, 'GROQ_MODEL', 'llama-3.3-70b-versatile')}")

    model = ChatGroq(
        model="llama-3.1-8b-instant",
        temperature=0.6,
        api_key=settings.GROQ_API_KEY,
    )

    # Список инструментов (сами функции, они используют глобальный контекст)
    tool_list = [tools.search_knowledge_base, tools.escalate_to_manager]
    model_with_tools = model.bind_tools(tool_list)

    async def call_model(state: AgentState):
        logger.debug(f"Agent invoked with {len(state['messages'])} messages")
        # Устанавливаем контекст для инструментов перед вызовом
        tools.set_current_context(state["project_id"], state["thread_id"])
        response = await model_with_tools.ainvoke(state["messages"])

        escalation = False
        if hasattr(response, "tool_calls") and response.tool_calls:
            for tc in response.tool_calls:
                if tc.get("name") == "escalate_to_manager":
                    escalation = True
                    break
        result = {"messages": [response]}
        if escalation:
            result["escalation_requested"] = True
        return result

    workflow = StateGraph(AgentState)
    workflow.add_node("agent", call_model)
    workflow.add_node("tools", ToolNode(tool_list))
    workflow.set_entry_point("agent")

    def should_continue(state: AgentState):
        last_message = state["messages"][-1]
        if last_message.tool_calls:
            return "tools"
        return END

    workflow.add_conditional_edges("agent", should_continue)
    workflow.add_edge("tools", "agent")

    compiled = workflow.compile()
    logger.info("Agent compiled successfully")
    return compiled
