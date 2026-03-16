import os
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_groq import ChatGroq  # Используем Groq
from .state import AgentState
from .tools import search_knowledge_base

def create_agent():
    # Инициализируем модель через Groq
    # API_KEY подтянется из переменной окружения GROQ_API_KEY
    model = ChatGroq(
        model="llama-3.3-70b-versatile",
        temperature=0.6,
        # groq_api_key=os.getenv("GROQ_API_KEY") # Можно явно, если .env не подхватился
    )

    # Привязываем твои инструменты
    tools = [search_knowledge_base]
    model_with_tools = model.bind_tools(tools)

    async def call_model(state: AgentState):
        response = await model_with_tools.ainvoke(state["messages"])
        return {"messages": [response]}

    # Дальше логика графа остается такой же - это и есть прелесть LangGraph
    workflow = StateGraph(AgentState)
    
    workflow.add_node("agent", call_model)
    workflow.add_node("tools", ToolNode(tools))
    
    workflow.set_entry_point("agent")
    
    def should_continue(state: AgentState):
        last_message = state["messages"][-1]
        if last_message.tool_calls:
            return "tools"
        return END

    workflow.add_conditional_edges("agent", should_continue)
    workflow.add_edge("tools", "agent")
    
    return workflow.compile()