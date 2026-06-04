from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Mapping

import pytest

from src.application.services.faq_workbench_retrieval_surface_publication_service import (
    PublishWorkbenchFactRetrievalSurfaceCommand,
    PublishWorkbenchFactRetrievalSurfaceResult,
)
from src.application.services.faq_workbench_runtime_publication_service import (
    FaqWorkbenchRuntimePublicationService,
    PublishFactRegistryRuntimeCommand,
)


@dataclass(slots=True)
class FakeWorkbenchRuntimeRepository:
    calls: list[tuple[str, str, object]] = field(default_factory=list)

    async def publish_fact_registry_runtime_entries(
        self,
        *,
        project_id: str,
        document_id: str,
        fact_registry_payload: object,
    ) -> int:
        self.calls.append((project_id, document_id, fact_registry_payload))
        return 2


@dataclass(slots=True)
class FakeRetrievalSurfacePublicationService:
    calls: list[PublishWorkbenchFactRetrievalSurfaceCommand] = field(
        default_factory=list
    )

    async def publish_workbench_fact_retrieval_surface(
        self,
        command: PublishWorkbenchFactRetrievalSurfaceCommand,
    ) -> PublishWorkbenchFactRetrievalSurfaceResult:
        self.calls.append(command)
        return PublishWorkbenchFactRetrievalSurfaceResult(
            built_entry_count=2,
            published_entry_count=2,
        )


def _fact_registry_payload() -> Mapping[str, object]:
    return {
        "canonical_facts": [
            {
                "fact_id": "fact-1",
                "claim": "Бот отвечает клиентам.",
                "answer": "Бот отвечает клиентам.",
                "status": "active",
            },
            {
                "fact_id": "fact-2",
                "claim": "Сложный вопрос передаётся менеджеру.",
                "answer": "Сложный вопрос передаётся менеджеру.",
                "status": "active",
            },
        ],
        "fact_relations": [],
    }


@pytest.mark.asyncio
async def test_runtime_publication_writes_debug_and_production_retrieval_projection_once() -> None:
    debug_repository = FakeWorkbenchRuntimeRepository()
    retrieval_surface = FakeRetrievalSurfacePublicationService()
    service = FaqWorkbenchRuntimePublicationService(
        debug_repository,
        retrieval_surface,
    )

    result = await service.publish_fact_registry_runtime_entries(
        PublishFactRegistryRuntimeCommand(
            project_id="project-1",
            document_id="document-1",
            fact_registry_payload=dict(_fact_registry_payload()),
        )
    )

    assert result.published_entry_count == 2
    assert result.published_retrieval_surface_entry_count == 2

    assert len(debug_repository.calls) == 1
    assert len(retrieval_surface.calls) == 1
    assert retrieval_surface.calls[0].project_id == "project-1"
    assert retrieval_surface.calls[0].document_id == "document-1"


@pytest.mark.asyncio
async def test_runtime_publication_keeps_legacy_debug_projection_when_surface_projection_disabled() -> None:
    debug_repository = FakeWorkbenchRuntimeRepository()
    service = FaqWorkbenchRuntimePublicationService(debug_repository)

    result = await service.publish_fact_registry_runtime_entries(
        PublishFactRegistryRuntimeCommand(
            project_id="project-1",
            document_id="document-1",
            fact_registry_payload=dict(_fact_registry_payload()),
        )
    )

    assert result.published_entry_count == 2
    assert result.published_retrieval_surface_entry_count == 0
    assert len(debug_repository.calls) == 1
