from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import cast

import pytest
from fastapi import UploadFile

from src.contexts.knowledge_workbench.application.sagas.run_source_ingestion_first_phase import (
    RunSourceIngestionFirstPhaseCommand,
)
from src.contexts.knowledge_workbench.application.sagas.source_ingestion_admission import (
    SourceIngestionActor,
)
from src.infrastructure.db.repositories.user_repository import UserRepository
from src.interfaces.composition.knowledge_extraction_workflow_after_upload import (
    RunKnowledgeExtractionWorkflowAfterUploadCommand,
    RunKnowledgeExtractionWorkflowAfterUploadResult,
)
from src.interfaces.http import knowledge


@dataclass(slots=True)
class FakeUploadFile:
    filename: str
    chunks: list[bytes]

    async def read(self, size: int) -> bytes:
        del size
        if not self.chunks:
            return b""
        return self.chunks.pop(0)


@dataclass(slots=True)
class FakeWorkflowRunner:
    calls: list[RunKnowledgeExtractionWorkflowAfterUploadCommand] = field(
        default_factory=list,
    )

    async def execute(
        self,
        command: RunKnowledgeExtractionWorkflowAfterUploadCommand,
    ) -> RunKnowledgeExtractionWorkflowAfterUploadResult:
        self.calls.append(command)
        return RunKnowledgeExtractionWorkflowAfterUploadResult(
            workflow_run_id="knowledge-extraction:source-document:project-1:test",
            source_ingestion_completed=True,
            drained_inspected_count=2,
            drained_dispatched_count=1,
            blocked_command_type="PREPARE_CLAIM_BUILDER_DISPATCH_BATCH",
            blocked_reason="COMMAND_HANDLER_NOT_IMPLEMENTED",
            source_document_ref="source-document:project-1:test",
            source_unit_count=1,
        )


@dataclass(slots=True)
class FactoryCall:
    pool: object
    project_repo: object
    user_repo: UserRepository


def _user_repository() -> UserRepository:
    return cast(UserRepository, object())


async def _fake_actor(
    *,
    authorization: str | None,
    user_repo: UserRepository,
) -> SourceIngestionActor:
    del authorization, user_repo
    return SourceIngestionActor(actor_user_id="owner-1", is_platform_admin=True)


def test_upload_handler_uses_after_upload_factory_not_manual_partial_runner() -> None:
    source = inspect.getsource(knowledge.upload_knowledge)

    assert "make_knowledge_extraction_workflow_after_upload(" in source
    assert "make_source_ingestion_first_phase(" not in source
    assert "RunKnowledgeExtractionWorkflowAfterUpload(" not in source


@pytest.mark.asyncio
async def test_upload_calls_production_after_upload_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = FakeWorkflowRunner()
    calls: list[FactoryCall] = []
    pool = object()
    project_repo = object()
    user_repo = _user_repository()

    def fake_factory(
        *,
        pool: object,
        project_repo: object,
        user_repo: UserRepository,
    ) -> FakeWorkflowRunner:
        calls.append(
            FactoryCall(
                pool=pool,
                project_repo=project_repo,
                user_repo=user_repo,
            )
        )
        return runner

    monkeypatch.setattr(
        knowledge,
        "_build_source_ingestion_actor",
        _fake_actor,
    )
    monkeypatch.setattr(
        knowledge,
        "make_knowledge_extraction_workflow_after_upload",
        fake_factory,
    )

    response = await knowledge.upload_knowledge(
        project_id="project-1",
        file=cast(
            UploadFile,
            FakeUploadFile(filename="knowledge.md", chunks=[b"# Title\n\nBody", b""]),
        ),
        preprocessing_mode="faq",
        authorization="Bearer fake",
        pool=pool,
        project_repo=project_repo,
        user_repo=user_repo,
    )

    assert len(calls) == 1
    assert calls[0].pool is pool
    assert calls[0].project_repo is project_repo
    assert calls[0].user_repo is user_repo
    assert len(runner.calls) == 1

    command = runner.calls[0].source_ingestion_command
    assert isinstance(command, RunSourceIngestionFirstPhaseCommand)
    assert command.project_id == "project-1"
    assert command.original_filename == "knowledge.md"
    assert command.raw_text == "# Title\n\nBody"
    assert response["status"] == "knowledge_extraction_workflow_started"
    assert response["blocked_command_type"] == "PREPARE_CLAIM_BUILDER_DISPATCH_BATCH"
    assert response["blocked_reason"] == "COMMAND_HANDLER_NOT_IMPLEMENTED"


@pytest.mark.asyncio
async def test_upload_without_llm_executor_keeps_explicit_blocked_behavior(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = FakeWorkflowRunner()
    pool = object()
    project_repo = object()
    user_repo = _user_repository()

    def fake_factory(
        *,
        pool: object,
        project_repo: object,
        user_repo: UserRepository,
    ) -> FakeWorkflowRunner:
        del pool, project_repo, user_repo
        return runner

    monkeypatch.setattr(
        knowledge,
        "_build_source_ingestion_actor",
        _fake_actor,
    )
    monkeypatch.setattr(
        knowledge,
        "make_knowledge_extraction_workflow_after_upload",
        fake_factory,
    )

    response = await knowledge.upload_knowledge(
        project_id="project-1",
        file=cast(
            UploadFile,
            FakeUploadFile(filename="knowledge.txt", chunks=[b"plain text", b""]),
        ),
        preprocessing_mode="faq",
        authorization=None,
        pool=pool,
        project_repo=project_repo,
        user_repo=user_repo,
    )

    assert response["source_ingestion_completed"] is True
    assert response["blocked_command_type"] == "PREPARE_CLAIM_BUILDER_DISPATCH_BATCH"
    assert response["blocked_reason"] == "COMMAND_HANDLER_NOT_IMPLEMENTED"
    assert response["source_units_url"] == (
        "/api/projects/project-1/knowledge/source-documents/"
        "source-document:project-1:test/source-units"
    )
