"""
Application-owned agent runtime ports.

The application layer must not import concrete LangGraph runtime modules.
Composition roots inject implementations matching these protocols.
"""

from typing import Protocol


AgentGraphState = dict[str, object]


class AgentGraphRuntimePort(Protocol):
    async def ainvoke(self, state: AgentGraphState) -> AgentGraphState:
        """Invoke the runtime graph with a typed state payload."""
        ...


class AgentFactoryPort(Protocol):
    def __call__(
        self,
        *,
        tool_registry: object | None = None,
        queue_repo: object | None = None,
        event_repo: object | None = None,
        project_repo: object | None = None,
        memory_repo: object | None = None,
    ) -> AgentGraphRuntimePort:
        """Create a runtime graph instance."""
        ...
