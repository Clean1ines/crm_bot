from typing import Annotated, Sequence, TypedDict
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    # add_messages значит, что новые сообщения будут добавляться к списку, а не перезаписывать его
    messages: Annotated[Sequence[BaseMessage], add_messages]
    project_id: str
    thread_id: str