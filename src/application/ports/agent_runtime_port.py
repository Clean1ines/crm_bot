"""
Application-owned agent runtime ports.

The application layer must not import concrete LangGraph runtime modules.
Composition roots inject implementations matching these protocols.
"""

from typing import Protocol

from src.domain.runtime.state_contracts import RuntimeStateInput


AgentGraphState = RuntimeStateInput


class AgentToolRegistryPort(Protocol):
    """Application-facing tool registry dependency injected into agent runtime."""


class AgentThreadLifecyclePort(Protocol):
    """Application-facing thread lifecycle dependency injected into agent runtime."""


class AgentThreadMessagePort(Protocol):
    """Application-facing thread message dependency injected into agent runtime."""


class AgentThreadRuntimeStatePort(Protocol):
    """Application-facing thread runtime-state dependency injected into agent runtime."""


class AgentThreadReadPort(Protocol):
    """Application-facing thread read dependency injected into agent runtime."""


class AgentQueuePort(Protocol):
    """Application-facing queue dependency injected into agent runtime."""


class AgentEventPort(Protocol):
    """Application-facing event dependency injected into agent runtime."""


class AgentProjectPort(Protocol):
    """Application-facing project dependency injected into agent runtime."""


class AgentMemoryPort(Protocol):
    """Application-facing memory dependency injected into agent runtime."""


class AgentGraphRuntimePort(Protocol):
    async def ainvoke(self, state: AgentGraphState) -> AgentGraphState:
        """Invoke the runtime graph with a typed state payload."""
        ...


class AgentFactoryPort(Protocol):
    def __call__(
        self,
        *,
        tool_registry: AgentToolRegistryPort | None = None,
        thread_lifecycle_repo: AgentThreadLifecyclePort | None = None,
        thread_message_repo: AgentThreadMessagePort | None = None,
        thread_runtime_state_repo: AgentThreadRuntimeStatePort | None = None,
        thread_read_repo: AgentThreadReadPort | None = None,
        queue_repo: AgentQueuePort | None = None,
        event_repo: AgentEventPort | None = None,
        project_repo: AgentProjectPort | None = None,
        memory_repo: AgentMemoryPort | None = None,
    ) -> AgentGraphRuntimePort:
        """Create a runtime graph instance."""
        ...
