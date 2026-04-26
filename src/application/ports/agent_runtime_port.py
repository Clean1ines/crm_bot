"""
Application-owned agent runtime ports.

The application layer must not import concrete LangGraph runtime modules.
Composition roots inject an implementation matching this protocol.
"""

from typing import Any, Protocol


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
    ) -> Any:
        """Create a runtime graph instance."""
        ...
