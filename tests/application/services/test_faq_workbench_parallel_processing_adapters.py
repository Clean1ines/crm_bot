from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from src.application.services.faq_workbench_canonicalization_barrier_service import (
    ProcessDocumentCanonicalizationBarrierCommand,
)
from src.application.services.faq_workbench_parallel_processing_adapters import (
    FaqWorkbenchCanonicalizationBarrierProcessorAdapter,
)
from src.application.services.faq_workbench_parallel_processing_coordinator_service import (
    ProcessParallelCanonicalizationBarrierCommand,
)


@dataclass(slots=True)
class FakeCanonicalizationBarrierService:
    commands: list[ProcessDocumentCanonicalizationBarrierCommand] = field(
        default_factory=list
    )
    result: str = "canonicalized"

    async def process_document_canonicalization_barrier(
        self,
        command: ProcessDocumentCanonicalizationBarrierCommand,
    ) -> str:
        self.commands.append(command)
        return self.result


@pytest.mark.asyncio
async def test_canonicalization_barrier_adapter_maps_parallel_command_to_document_barrier_command() -> (
    None
):
    barrier_service = FakeCanonicalizationBarrierService(result="canonicalized")
    adapter = FaqWorkbenchCanonicalizationBarrierProcessorAdapter(
        barrier_service=barrier_service,
    )

    result = await adapter.process_document_canonicalization_barrier(
        ProcessParallelCanonicalizationBarrierCommand(
            project_id="project-1",
            document_id="document-1",
            processing_run_id="processing-run-1",
            worker_id="worker-canonicalization-1",
            lease_seconds=123,
        )
    )

    assert result == "canonicalized"
    assert barrier_service.commands == [
        ProcessDocumentCanonicalizationBarrierCommand(
            project_id="project-1",
            document_id="document-1",
            processing_run_id="processing-run-1",
            worker_id="worker-canonicalization-1",
            lease_seconds=123,
        )
    ]


def test_parallel_processing_adapters_export_canonicalization_barrier_adapter_without_legacy_section_merge() -> (
    None
):
    import src.application.services.faq_workbench_parallel_processing_adapters as module

    assert hasattr(module, "FaqWorkbenchCanonicalizationBarrierProcessorAdapter")
    assert not hasattr(module, "FaqWorkbenchRegistryMergeRunner")
    assert not hasattr(module, "FaqWorkbenchSectionFindingsRunner")
