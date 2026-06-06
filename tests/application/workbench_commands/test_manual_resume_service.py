from __future__ import annotations

from pathlib import Path

from datetime import datetime, timezone

import pytest

from src.application.workbench.dto import (
    WorkbenchProcessDocumentJobPayloadDto,
    WorkbenchProcessDocumentJobSource,
)
from src.application.workbench_commands.manual_resume import (
    WorkbenchManualResumeCommand,
    WorkbenchManualResumeNotFoundError,
    WorkbenchManualResumeRejectedError,
    WorkbenchManualResumeService,
)
from src.domain.project_plane.knowledge_workbench import (
    KnowledgeDocument,
    KnowledgeDocumentStatus,
    KnowledgeProcessingRun,
    ProcessingMethod,
    ProcessingRunStatus,
    ProcessingTrigger,
    ResumePolicy,
    SourceType,
)


def _now() -> datetime:
    return datetime(2026, 5, 31, tzinfo=timezone.utc)


def _document(
    *,
    status: KnowledgeDocumentStatus = KnowledgeDocumentStatus.CANCELLED,
    current_processing_run_id: str | None = "processing-run-1",
) -> KnowledgeDocument:
    return KnowledgeDocument(
        document_id="document-1",
        project_id="project-1",
        file_name="knowledge.md",
        source_type=SourceType.MARKDOWN,
        content_hash="hash-1",
        upload_id="upload-1",
        file_size_bytes=128,
        status=status,
        current_processing_run_id=current_processing_run_id,
        deleted_at=_now() if status is KnowledgeDocumentStatus.DELETED else None,
    )


def _run(
    *,
    processing_run_id: str = "processing-run-1",
    document_id: str = "document-1",
    status: ProcessingRunStatus = ProcessingRunStatus.CANCELLED_BY_USER,
    resume_policy: ResumePolicy = ResumePolicy.MANUAL_ONLY,
) -> KnowledgeProcessingRun:
    return KnowledgeProcessingRun(
        processing_run_id=processing_run_id,
        project_id="project-1",
        document_id=document_id,
        processing_method=ProcessingMethod.FAQ_SECTION_REGISTRY_V1,
        trigger=ProcessingTrigger.EXPLICIT_USER_RESUME,
        status=status,
        resume_policy=resume_policy,
    )


class FakeRepository:
    def __init__(
        self,
        *,
        document: KnowledgeDocument | None = None,
        run: KnowledgeProcessingRun | None = None,
    ) -> None:
        self.document = _document() if document is None else document
        self.run = _run() if run is None else run
        self.calls: list[str] = []

    async def get_document(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> KnowledgeDocument | None:
        self.calls.append(f"document:{project_id}:{document_id}")
        return self.document

    async def get_processing_run(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
    ) -> KnowledgeProcessingRun | None:
        self.calls.append(f"run:{project_id}:{document_id}:{processing_run_id}")
        return self.run

    async def persist_processing_manual_resume_transition(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str,
    ) -> None:
        self.calls.append(
            f"resume-transition:{project_id}:{document_id}:{processing_run_id}"
        )


class MissingDocumentRepository(FakeRepository):
    def __init__(self) -> None:
        super().__init__()
        self.document = None


class MissingRunRepository(FakeRepository):
    def __init__(self) -> None:
        super().__init__()
        self.run = None


class FakeQueue:
    def __init__(self) -> None:
        self.payloads: list[WorkbenchProcessDocumentJobPayloadDto] = []

    async def enqueue_process_workbench_document(
        self,
        payload: WorkbenchProcessDocumentJobPayloadDto,
    ) -> None:
        self.payloads.append(payload)


@pytest.mark.asyncio
async def test_manual_resume_reuses_current_run_and_enqueues_workbench_resume() -> None:
    queue = FakeQueue()
    repository = FakeRepository()

    result = await WorkbenchManualResumeService(
        repository,
        queue,
    ).resume_document(
        WorkbenchManualResumeCommand(
            project_id="project-1",
            document_id="document-1",
        )
    )

    assert result.to_dict() == {
        "project_id": "project-1",
        "document_id": "document-1",
        "processing_run_id": "processing-run-1",
        "status": "queued",
        "source": "workbench_explicit_user_resume",
        "resume_policy": "manual_only",
        "reason": "explicit user resume may resume only manual-only cancelled runs",
    }
    assert repository.calls == [
        "document:project-1:document-1",
        "run:project-1:document-1:processing-run-1",
        "resume-transition:project-1:document-1:processing-run-1",
    ]
    assert len(queue.payloads) == 1
    payload = queue.payloads[0]
    assert payload.trigger is ProcessingTrigger.EXPLICIT_USER_RESUME
    assert payload.source is WorkbenchProcessDocumentJobSource.EXPLICIT_USER_RESUME
    assert payload.processing_run_id == "processing-run-1"


@pytest.mark.asyncio
async def test_manual_resume_raises_not_found_for_missing_document() -> None:
    queue = FakeQueue()
    repository = MissingDocumentRepository()

    with pytest.raises(WorkbenchManualResumeNotFoundError):
        await WorkbenchManualResumeService(repository, queue).resume_document(
            WorkbenchManualResumeCommand(
                project_id="project-1",
                document_id="document-1",
            )
        )

    assert queue.payloads == []


@pytest.mark.asyncio
async def test_manual_resume_rejects_document_without_current_run() -> None:
    queue = FakeQueue()
    repository = FakeRepository(
        document=_document(current_processing_run_id=None),
    )

    with pytest.raises(
        WorkbenchManualResumeRejectedError,
        match="no current processing run",
    ):
        await WorkbenchManualResumeService(repository, queue).resume_document(
            WorkbenchManualResumeCommand(
                project_id="project-1",
                document_id="document-1",
            )
        )

    assert queue.payloads == []


@pytest.mark.asyncio
async def test_manual_resume_rejects_missing_current_run_record() -> None:
    queue = FakeQueue()
    repository = MissingRunRepository()

    with pytest.raises(
        WorkbenchManualResumeRejectedError,
        match="resume requested but no existing run was provided",
    ):
        await WorkbenchManualResumeService(repository, queue).resume_document(
            WorkbenchManualResumeCommand(
                project_id="project-1",
                document_id="document-1",
            )
        )

    assert queue.payloads == []


@pytest.mark.asyncio
async def test_manual_resume_rejects_wrong_processing_run_id() -> None:
    queue = FakeQueue()
    repository = FakeRepository(run=_run(processing_run_id="other-run"))

    with pytest.raises(
        WorkbenchManualResumeRejectedError,
        match="resume requires explicit same processing_run_id",
    ):
        await WorkbenchManualResumeService(repository, queue).resume_document(
            WorkbenchManualResumeCommand(
                project_id="project-1",
                document_id="document-1",
            )
        )

    assert queue.payloads == []


@pytest.mark.asyncio
async def test_manual_resume_rejects_wrong_document_id() -> None:
    queue = FakeQueue()
    repository = FakeRepository(run=_run(document_id="other-document"))

    with pytest.raises(
        WorkbenchManualResumeRejectedError,
        match="resume requires the same document_id",
    ):
        await WorkbenchManualResumeService(repository, queue).resume_document(
            WorkbenchManualResumeCommand(
                project_id="project-1",
                document_id="document-1",
            )
        )

    assert queue.payloads == []


@pytest.mark.asyncio
async def test_manual_resume_rejects_non_manual_resume_policy() -> None:
    queue = FakeQueue()
    repository = FakeRepository(
        run=_run(
            status=ProcessingRunStatus.PAUSED_QUOTA,
            resume_policy=ResumePolicy.AUTO_ALLOWED,
        )
    )

    with pytest.raises(
        WorkbenchManualResumeRejectedError,
        match="manual-only cancelled runs",
    ):
        await WorkbenchManualResumeService(repository, queue).resume_document(
            WorkbenchManualResumeCommand(
                project_id="project-1",
                document_id="document-1",
            )
        )

    assert queue.payloads == []


@pytest.mark.asyncio
async def test_manual_resume_rejects_deleted_document() -> None:
    queue = FakeQueue()
    repository = FakeRepository(
        document=_document(status=KnowledgeDocumentStatus.DELETED),
    )

    with pytest.raises(
        WorkbenchManualResumeRejectedError,
        match="deleted document cannot be resumed",
    ):
        await WorkbenchManualResumeService(repository, queue).resume_document(
            WorkbenchManualResumeCommand(
                project_id="project-1",
                document_id="document-1",
            )
        )

    assert queue.payloads == []


def test_manual_resume_service_is_queue_type_agnostic() -> None:
    source = Path("src/application/workbench_commands/manual_resume.py").read_text()

    assert "WorkbenchQueueAdapter" not in source
    assert "WorkbenchParallelQueueAdapter" not in source
    assert "src.infrastructure.queue.workbench_queue" not in source
    assert "src.infrastructure.queue.workbench_parallel_queue" not in source
