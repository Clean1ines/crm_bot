from __future__ import annotations

import pytest

from src.application.services.faq_workbench_registry_application_queue_service import (
    FaqWorkbenchRegistryApplicationQueueService,
    RetiredRegistryApplicationQueueServiceCommand,
    RetiredRegistryApplicationQueueServiceError,
)


def test_retired_registry_application_queue_service_command_is_importable_marker() -> (
    None
):
    command = RetiredRegistryApplicationQueueServiceCommand()

    assert command.reason == "registry application queue service is retired"


@pytest.mark.asyncio
async def test_retired_registry_application_queue_service_fails_explicitly() -> None:
    service = FaqWorkbenchRegistryApplicationQueueService(
        repository=object(),
        registry_application_service=object(),
    )

    with pytest.raises(
        RetiredRegistryApplicationQueueServiceError,
        match="use FaqWorkbenchRegistryApplicationWorkItemProcessorService",
    ):
        await service.process_next_registry_application_queue_item()


@pytest.mark.asyncio
async def test_retired_registry_application_queue_service_unknown_methods_fail_explicitly() -> (
    None
):
    service = FaqWorkbenchRegistryApplicationQueueService()

    with pytest.raises(
        RetiredRegistryApplicationQueueServiceError,
        match="Prompt C fact_registry artifacts",
    ):
        await service.some_old_method()
