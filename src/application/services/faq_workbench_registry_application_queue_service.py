from __future__ import annotations

from dataclasses import dataclass

from src.domain.project_plane.knowledge_workbench import DomainInvariantError


class RetiredRegistryApplicationQueueServiceError(DomainInvariantError):
    """Raised when retired Python-level registry application is invoked."""


@dataclass(frozen=True, slots=True)
class RetiredRegistryApplicationQueueServiceCommand:
    """Compatibility marker for old imports.

    The old service applied Python-level surface/question objects directly.
    That semantic path is retired. The production path is now:

    registry application queue item
    -> FaqWorkbenchRegistryApplicationWorkItemProcessorService
    -> parsed Prompt C fact_registry artifact
    -> FaqWorkbenchRegistryApplicationService.apply_fact_registry_snapshot
    """

    reason: str = "registry application queue service is retired"


class FaqWorkbenchRegistryApplicationQueueService:
    """Retired compatibility guard.

    Do not add new behavior here. This class exists only to make stale imports fail
    explicitly at runtime instead of silently reviving the old surface/question
    registry merge path.
    """

    def __init__(self, *args: object, **kwargs: object) -> None:
        self._args = args
        self._kwargs = kwargs

    async def process_next_registry_application_queue_item(
        self,
        *args: object,
        **kwargs: object,
    ) -> None:
        raise _retired_error()

    async def process_registry_application_queue_item(
        self,
        *args: object,
        **kwargs: object,
    ) -> None:
        raise _retired_error()

    async def apply_registry_application_queue_item(
        self,
        *args: object,
        **kwargs: object,
    ) -> None:
        raise _retired_error()

    def __getattr__(self, name: str) -> object:
        if name.startswith("_"):
            raise AttributeError(name)

        async def _retired_method(*args: object, **kwargs: object) -> None:
            raise _retired_error()

        return _retired_method


def _retired_error() -> RetiredRegistryApplicationQueueServiceError:
    return RetiredRegistryApplicationQueueServiceError(
        "FaqWorkbenchRegistryApplicationQueueService is retired; "
        "use FaqWorkbenchRegistryApplicationWorkItemProcessorService with "
        "Prompt C fact_registry artifacts"
    )


__all__ = [
    "FaqWorkbenchRegistryApplicationQueueService",
    "RetiredRegistryApplicationQueueServiceCommand",
    "RetiredRegistryApplicationQueueServiceError",
]
