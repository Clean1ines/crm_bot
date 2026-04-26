"""
Application-owned agent runtime ports.

The application layer must not import concrete LangGraph runtime modules.
Composition roots inject implementations matching these protocols.
"""

from typing import Any, Protocol


class AgentGraphRuntimePort(Protocol):
    async def ainvoke(self, state: dict[str, Any]) -> dict[str, Any]:
        """Invoke the runtime graph with a typed state payload."""
        ...


class AgentFactoryPort(Protocol):
    def __call__(
        self,
        *,
        tool_registry: Any = None,
        thread_repo: Any = None,
        queue_repo: Any = None,
        event_repo: Any = None,
        project_repo: Any = None,
        memory_repo: Any = None,
    ) -> AgentGraphRuntimePort:
        """Create a runtime graph instance."""
        ...
