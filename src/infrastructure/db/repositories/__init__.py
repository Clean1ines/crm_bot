from __future__ import annotations

from importlib import import_module

_EXPORT_MODULES: dict[str, str] = {
    "ClientRepository": "src.infrastructure.db.repositories.client_repository",
    "EventRepository": "src.infrastructure.db.repositories.event_repository",
    "KnowledgeRepository": "src.infrastructure.db.repositories.knowledge_repository",
    "MemoryRepository": "src.infrastructure.db.repositories.memory_repository",
    "MetricsRepository": "src.infrastructure.db.repositories.metrics_repository",
    "ProjectChannelRepository": "src.infrastructure.db.repositories.project",
    "ProjectCommandRepository": "src.infrastructure.db.repositories.project",
    "ProjectConfigurationRepository": "src.infrastructure.db.repositories.project",
    "ProjectIntegrationRepository": "src.infrastructure.db.repositories.project",
    "ProjectMemberRepository": "src.infrastructure.db.repositories.project",
    "ProjectQueryRepository": "src.infrastructure.db.repositories.project",
    "ProjectRepository": "src.infrastructure.db.repositories.project",
    "ProjectRepositoryBase": "src.infrastructure.db.repositories.project",
    "ProjectTokenRepository": "src.infrastructure.db.repositories.project",
    "QueueRepository": "src.infrastructure.db.repositories.queue_repository",
    "ThreadRuntimeStateRepository": (
        "src.infrastructure.db.repositories.thread.runtime_state"
    ),
    "UserRepository": "src.infrastructure.db.repositories.user_repository",
}

__all__ = sorted(_EXPORT_MODULES)


def __getattr__(name: str) -> object:
    module_path = _EXPORT_MODULES.get(name)
    if module_path is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module = import_module(module_path)
    value = getattr(module, name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted((*globals(), *__all__))
