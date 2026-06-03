from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.application.services.faq_workbench_fresh_upload_service import (
    FaqWorkbenchFreshUploadCommand,
    FaqWorkbenchFreshUploadService,
    MonotonicIdFactory,
)
from src.domain.project_plane.knowledge_workbench import (
    DomainInvariantError,
    KnowledgeDocumentStatus,
    ProcessingMethod,
    ProcessingNodeArtifactType,
    ProcessingNodeName,
    ProcessingRunStatus,
    ProcessingTrigger,
    FactRegistryStatus,
    ResumePolicy,
)
from tests.application.workbench.helpers import (
    FixedTimeProvider,
    InMemoryWorkbenchRepository,
)


@pytest.mark.asyncio
async def test_fresh_markdown_upload_creates_workbench_document_sections_run_and_snapshot() -> (
    None
):
    repository = InMemoryWorkbenchRepository()
    service = FaqWorkbenchFreshUploadService(
        repository,
        id_factory=MonotonicIdFactory.create(),
        time_provider=FixedTimeProvider(datetime(2026, 5, 31, tzinfo=timezone.utc)),
    )

    result = await service.start_fresh_upload(
        FaqWorkbenchFreshUploadCommand(
            project_id="project-1",
            file_name="ai_manager_knowledge_base.md",
            upload_id="upload-1",
            raw_text="# Product\nSystem turns docs into knowledge.\n\n## Curation\nUsers review surfaces.",
            file_size_bytes=len(
                b"# Product\nSystem turns docs into knowledge.\n\n## Curation\nUsers review surfaces."
            ),
        )
    )

    assert result.document.status is KnowledgeDocumentStatus.SECTIONED
    assert result.document.file_size_bytes == len(
        b"# Product\nSystem turns docs into knowledge.\n\n## Curation\nUsers review surfaces."
    )
    assert (
        result.document.current_processing_run_id
        == result.processing_run.processing_run_id
    )
    assert result.processing_run.trigger is ProcessingTrigger.FRESH_UPLOAD
    assert result.processing_run.resume_policy is ResumePolicy.FORBIDDEN
    assert result.processing_run.status is ProcessingRunStatus.RUNNING
    assert (
        result.processing_run.processing_method
        is ProcessingMethod.FAQ_SECTION_REGISTRY_V1
    )

    assert len(result.sections) == 2
    assert result.sections[0].title == "Product"
    assert result.sections[1].title == "Curation"
    assert result.sections[1].parent_section_id == result.sections[0].section_id

    assert result.registry.status is FactRegistryStatus.BUILDING
    assert (
        result.initialize_node_run.node_name is ProcessingNodeName.INITIALIZE_REGISTRY
    )
    assert (
        result.initialize_artifact.artifact_type
        is ProcessingNodeArtifactType.APPLIED_RESULT
    )
    assert result.initial_snapshot.entry_count == 0

    assert repository.documents == [result.document]
    assert tuple(repository.sections) == result.sections
    assert repository.runs == [result.processing_run]
    assert repository.registries == [result.registry]
    assert repository.node_runs == [result.initialize_node_run]
    assert repository.artifacts == [result.initialize_artifact]
    assert repository.snapshots == [result.initial_snapshot]


@pytest.mark.asyncio
async def test_fresh_upload_does_not_accept_empty_markdown() -> None:
    repository = InMemoryWorkbenchRepository()
    service = FaqWorkbenchFreshUploadService(
        repository,
        id_factory=MonotonicIdFactory.create(),
    )

    with pytest.raises(DomainInvariantError):
        await service.start_fresh_upload(
            FaqWorkbenchFreshUploadCommand(
                project_id="project-1",
                file_name="empty.md",
                upload_id="upload-1",
                raw_text="   ",
                file_size_bytes=3,
            )
        )

    assert repository.documents == []
    assert repository.runs == []
    assert repository.snapshots == []


@pytest.mark.asyncio
async def test_markdown_without_headings_becomes_single_document_section() -> None:
    repository = InMemoryWorkbenchRepository()
    service = FaqWorkbenchFreshUploadService(
        repository,
        id_factory=MonotonicIdFactory.create(),
    )

    result = await service.start_fresh_upload(
        FaqWorkbenchFreshUploadCommand(
            project_id="project-1",
            file_name="plain.md",
            upload_id="upload-1",
            raw_text="Just a plain markdown note.",
            file_size_bytes=len(b"Just a plain markdown note."),
        )
    )

    assert len(result.sections) == 1
    assert result.sections[0].title == "Document"
    assert result.sections[0].heading_path == ("Document",)
