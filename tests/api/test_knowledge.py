from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import ClassVar, cast

import pytest
from fastapi import HTTPException, UploadFile
from src.contexts.knowledge_workbench.application.sagas.run_source_ingestion_first_phase import (
    RunSourceIngestionFirstPhaseCommand,
    RunSourceIngestionFirstPhaseResult,
    RunSourceIngestionFirstPhaseStatus,
)
from src.contexts.knowledge_workbench.application.sagas.source_ingestion_workflow_effects import (
    BuildSourceIngestionWorkflowEffects,
    BuildSourceIngestionWorkflowEffectsCommand,
)
from src.contexts.knowledge_workbench.extraction.application.ports.draft_claim_observation_read_repository_port import (
    DraftClaimObservationReadModel,
)
from src.contexts.knowledge_workbench.application.sagas.source_ingestion_admission import (
    SourceIngestionAdmissionStatus,
)
from src.contexts.knowledge_workbench.source_management.domain.entities.source_unit import (
    SourceUnit,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.heading_path import (
    HeadingPath,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_document_ref import (
    SourceDocumentRef,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_kind import (
    SourceUnitKind,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_lineage import (
    SourceUnitLineage,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_ref import (
    SourceUnitRef,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_text import (
    SourceUnitText,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_format import (
    SourceFormat,
)
from src.infrastructure.db.repositories.user_repository import UserRepository
from src.interfaces.composition.knowledge_extraction_workflow_after_upload import (
    RunKnowledgeExtractionWorkflowAfterUploadCommand,
    RunKnowledgeExtractionWorkflowAfterUploadResult,
)
from src.interfaces.http import dependencies, knowledge


@dataclass(slots=True)
class _FakeProjectRepo:
    exists: bool = True
    has_role: bool = True

    async def project_exists(self, project_id: str) -> bool:
        return self.exists

    async def user_has_project_role(
        self,
        project_id: str,
        user_id: str,
        allowed_roles: tuple[str, ...],
    ) -> bool:
        return self.has_role


@dataclass(slots=True)
class _FakeUserRepo:
    platform_admin: bool = False

    async def is_platform_admin(self, user_id: str) -> bool:
        return self.platform_admin


def _user_repo(*, platform_admin: bool = False) -> UserRepository:
    return cast(UserRepository, _FakeUserRepo(platform_admin=platform_admin))


class _FakeSourceManagementRepository:
    def __init__(self, units: tuple[SourceUnit, ...]) -> None:
        self.units = units
        self.document_refs: list[SourceDocumentRef] = []

    async def list_source_units_for_document(
        self,
        document_ref: SourceDocumentRef,
    ) -> tuple[SourceUnit, ...]:
        self.document_refs.append(document_ref)
        return self.units


class _FakeSourceIngestionRunner:
    def __init__(self, result: RunSourceIngestionFirstPhaseResult) -> None:
        self.result = result
        self.commands: list[RunSourceIngestionFirstPhaseCommand] = []

    async def execute(
        self,
        command: RunSourceIngestionFirstPhaseCommand,
    ) -> RunSourceIngestionFirstPhaseResult:
        self.commands.append(command)
        return self.result


class _FakeWorkflowAfterUploadRunner:
    instances: list[_FakeWorkflowAfterUploadRunner] = []

    def __init__(
        self,
        *,
        source_ingestion_runner: _FakeSourceIngestionRunner,
        pool: object,
    ) -> None:
        self.source_ingestion_runner = source_ingestion_runner
        self.pool = pool
        self.commands: list[RunKnowledgeExtractionWorkflowAfterUploadCommand] = []
        _FakeWorkflowAfterUploadRunner.instances.append(self)

    async def execute(
        self,
        command: RunKnowledgeExtractionWorkflowAfterUploadCommand,
    ) -> RunKnowledgeExtractionWorkflowAfterUploadResult:
        self.commands.append(command)
        source_result = await self.source_ingestion_runner.execute(
            command.source_ingestion_command,
        )
        if source_result.status is RunSourceIngestionFirstPhaseStatus.REJECTED:
            return RunKnowledgeExtractionWorkflowAfterUploadResult(
                workflow_run_id="",
                source_ingestion_completed=False,
                drained_inspected_count=0,
                drained_dispatched_count=0,
                blocked_command_type=None,
                blocked_reason=None,
                source_document_ref=None,
                source_unit_count=0,
                source_ingestion_admission_status=source_result.admission_status,
            )

        return RunKnowledgeExtractionWorkflowAfterUploadResult(
            workflow_run_id=source_result.workflow_run_id or "",
            source_ingestion_completed=True,
            drained_inspected_count=2,
            drained_dispatched_count=1,
            blocked_command_type="PrepareClaimBuilderDispatchBatch",
            blocked_reason="COMMAND_HANDLER_NOT_IMPLEMENTED",
            source_document_ref=source_result.source_document_ref,
            source_unit_count=source_result.source_unit_count,
            source_ingestion_admission_status=source_result.admission_status,
        )


def _patch_after_upload_factory(
    monkeypatch: pytest.MonkeyPatch,
    *,
    runner: _FakeSourceIngestionRunner,
    factory_calls: list[dict[str, object]] | None = None,
) -> None:
    def fake_make_knowledge_extraction_workflow_after_upload(
        **kwargs: object,
    ) -> _FakeWorkflowAfterUploadRunner:
        if factory_calls is not None:
            factory_calls.append(kwargs)
        return _FakeWorkflowAfterUploadRunner(
            source_ingestion_runner=runner,
            pool=kwargs["pool"],
        )

    monkeypatch.setattr(
        knowledge,
        "make_knowledge_extraction_workflow_after_upload",
        fake_make_knowledge_extraction_workflow_after_upload,
    )


@dataclass(slots=True)
class _FakeDraftClaimObservationReadRepository:
    items: tuple[DraftClaimObservationReadModel, ...] = ()
    document_calls: list[dict[str, object]] = field(default_factory=list)
    source_unit_calls: list[dict[str, object]] = field(default_factory=list)

    instances: ClassVar[list[_FakeDraftClaimObservationReadRepository]] = []
    configured_items: ClassVar[tuple[DraftClaimObservationReadModel, ...]] = ()

    def __init__(self, pool: object) -> None:
        del pool
        self.items = self.configured_items
        self.document_calls = []
        self.source_unit_calls = []
        self.instances.append(self)

    async def list_by_source_document_ref(
        self,
        *,
        source_document_ref: str,
        limit: int,
        offset: int,
    ) -> tuple[DraftClaimObservationReadModel, ...]:
        self.document_calls.append(
            {
                "source_document_ref": source_document_ref,
                "limit": limit,
                "offset": offset,
            }
        )
        return self.items[offset : offset + limit]

    async def list_by_source_unit_ref(
        self,
        *,
        source_unit_ref: str,
        limit: int,
        offset: int,
    ) -> tuple[DraftClaimObservationReadModel, ...]:
        self.source_unit_calls.append(
            {
                "source_unit_ref": source_unit_ref,
                "limit": limit,
                "offset": offset,
            }
        )
        return tuple(
            item for item in self.items if item.source_unit_ref == source_unit_ref
        )[offset : offset + limit]


def _draft_claim_read_model(
    *,
    observation_ref: str = "draft-claim-observation:1",
    source_unit_ref: str = "source-unit:1",
    claim: str = "System turns documents into knowledge.",
    claim_index: int | None = 0,
) -> DraftClaimObservationReadModel:
    return DraftClaimObservationReadModel(
        observation_ref=observation_ref,
        source_unit_ref=source_unit_ref,
        claim=claim,
        granularity="atomic",
        possible_questions=("What does the system do?",),
        exclusion_scope="",
        evidence_block="System turns documents into knowledge.",
        workflow_run_id="workflow-1",
        stage_run_id="claim_builder_section_extraction",
        work_item_id="work-1",
        work_item_attempt_id="work-1:attempt-1",
        llm_task_id="work-1",
        llm_attempt_id="work-1:attempt-1",
        prompt_id="faq_claim_observations",
        prompt_version="v1",
        claim_index=claim_index,
        created_at=datetime(2026, 6, 13, 12, 0, tzinfo=timezone.utc),
    )


def _completed_source_ingestion_result() -> RunSourceIngestionFirstPhaseResult:
    return RunSourceIngestionFirstPhaseResult(
        status=RunSourceIngestionFirstPhaseStatus.COMPLETED,
        admission_status=SourceIngestionAdmissionStatus.ALLOWED,
        workflow_run_id="knowledge-extraction:source-document:project-1:abc",
        source_document_ref="source-document:project-1:abc",
        source_unit_count=3,
        workflow_effects=BuildSourceIngestionWorkflowEffects().execute(
            BuildSourceIngestionWorkflowEffectsCommand(
                workflow_run_id="knowledge-extraction:source-document:project-1:abc",
                project_id="project-1",
                source_document_ref="source-document:project-1:abc",
                source_unit_count=3,
                source_format=SourceFormat.MARKDOWN,
                content_hash="sha256:test",
                occurred_at=datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc),
            )
        ),
    )


def _rejected_source_ingestion_result(
    status: SourceIngestionAdmissionStatus,
) -> RunSourceIngestionFirstPhaseResult:
    return RunSourceIngestionFirstPhaseResult(
        status=RunSourceIngestionFirstPhaseStatus.REJECTED,
        admission_status=status,
    )


def _source_unit(
    *,
    unit_ref: str,
    ordinal: int,
    unit_kind: SourceUnitKind,
    heading_path: tuple[str, ...],
    text: str,
    document_ref: str = "source-document:project-1:abc",
) -> SourceUnit:
    return SourceUnit(
        unit_ref=SourceUnitRef(unit_ref),
        document_ref=SourceDocumentRef(document_ref),
        unit_kind=unit_kind,
        text=SourceUnitText(text),
        heading_path=HeadingPath(heading_path),
        lineage=SourceUnitLineage(),
        ordinal=ordinal,
        created_at=datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc),
    )


def _upload_file(
    *,
    file_name: str = "faq.md",
    content: bytes = b"# FAQ\nAnswer",
) -> UploadFile:
    return UploadFile(filename=file_name, file=BytesIO(content))


def _source() -> str:
    return Path("src/interfaces/http/knowledge.py").read_text(encoding="utf-8")


def test_source_units_url_uses_project_and_source_document_ref() -> None:
    assert knowledge._source_units_url(
        project_id="project-1",
        source_document_ref="source-document:project-1:abc",
    ) == (
        "/api/projects/project-1/knowledge/source-documents/"
        "source-document:project-1:abc/source-units"
    )


@pytest.mark.asyncio
async def test_upload_success_uses_workflow_after_upload_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_current_user_id(authorization: str | None) -> str:
        assert authorization == "Bearer valid-token"
        return "user-1"

    runner = _FakeSourceIngestionRunner(_completed_source_ingestion_result())
    factory_calls: list[dict[str, object]] = []
    _FakeWorkflowAfterUploadRunner.instances = []

    monkeypatch.setattr(dependencies, "get_current_user_id", fake_current_user_id)
    _patch_after_upload_factory(
        monkeypatch,
        runner=runner,
        factory_calls=factory_calls,
    )

    response = await knowledge.upload_knowledge(
        project_id="project-1",
        file=_upload_file(file_name="faq.md", content=b"# FAQ\nAnswer"),
        preprocessing_mode="faq",
        authorization="Bearer valid-token",
        pool=object(),
        project_repo=_FakeProjectRepo(),
        user_repo=_user_repo(platform_admin=True),
    )

    assert response == {
        "status": "knowledge_extraction_workflow_started",
        "workflow_run_id": "knowledge-extraction:source-document:project-1:abc",
        "source_ingestion_completed": True,
        "drained_inspected_count": 2,
        "drained_dispatched_count": 1,
        "blocked_command_type": "PrepareClaimBuilderDispatchBatch",
        "blocked_reason": "COMMAND_HANDLER_NOT_IMPLEMENTED",
        "source_document_ref": "source-document:project-1:abc",
        "source_unit_count": 3,
        "source_units_url": (
            "/api/projects/project-1/knowledge/source-documents/"
            "source-document:project-1:abc/source-units"
        ),
        "draft_claims_url": (
            "/api/projects/project-1/knowledge/source-documents/"
            "source-document:project-1:abc/draft-claims"
        ),
    }
    assert len(factory_calls) == 1
    assert len(_FakeWorkflowAfterUploadRunner.instances) == 1
    assert _FakeWorkflowAfterUploadRunner.instances[0].pool is not None
    assert len(_FakeWorkflowAfterUploadRunner.instances[0].commands) == 1
    assert len(runner.commands) == 1

    workflow_command = _FakeWorkflowAfterUploadRunner.instances[0].commands[0]
    assert workflow_command.max_drain_commands == 10
    command = workflow_command.source_ingestion_command
    assert command.project_id == "project-1"
    assert command.actor.actor_user_id == "user-1"
    assert command.actor.is_platform_admin is True
    assert command.content_bytes == b"# FAQ\nAnswer"
    assert command.raw_text == "# FAQ\nAnswer"
    assert command.original_filename == "faq.md"
    assert command.source_format is SourceFormat.MARKDOWN
    assert command.segmentation_budget is None
    assert command.occurred_at.tzinfo is not None


@pytest.mark.asyncio
async def test_upload_rejected_missing_project_maps_to_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_current_user_id(authorization: str | None) -> str:
        return "user-1"

    runner = _FakeSourceIngestionRunner(
        _rejected_source_ingestion_result(
            SourceIngestionAdmissionStatus.PROJECT_NOT_FOUND,
        )
    )

    monkeypatch.setattr(dependencies, "get_current_user_id", fake_current_user_id)
    _patch_after_upload_factory(monkeypatch, runner=runner)

    with pytest.raises(HTTPException) as exc_info:
        await knowledge.upload_knowledge(
            project_id="missing-project",
            file=_upload_file(),
            preprocessing_mode="faq",
            authorization="Bearer valid-token",
            pool=object(),
            project_repo=_FakeProjectRepo(),
            user_repo=_user_repo(),
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "PROJECT_NOT_FOUND"


@pytest.mark.asyncio
async def test_upload_rejected_unauthenticated_maps_to_401(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_current_user_id(authorization: str | None) -> str:
        return "user-1"

    runner = _FakeSourceIngestionRunner(
        _rejected_source_ingestion_result(
            SourceIngestionAdmissionStatus.ACTOR_NOT_AUTHENTICATED,
        )
    )

    monkeypatch.setattr(dependencies, "get_current_user_id", fake_current_user_id)
    _patch_after_upload_factory(monkeypatch, runner=runner)

    with pytest.raises(HTTPException) as exc_info:
        await knowledge.upload_knowledge(
            project_id="project-1",
            file=_upload_file(),
            preprocessing_mode="faq",
            authorization="Bearer valid-token",
            pool=object(),
            project_repo=_FakeProjectRepo(),
            user_repo=_user_repo(),
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "ACTOR_NOT_AUTHENTICATED"


@pytest.mark.asyncio
async def test_upload_rejected_role_denied_maps_to_403(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_current_user_id(authorization: str | None) -> str:
        return "user-1"

    runner = _FakeSourceIngestionRunner(
        _rejected_source_ingestion_result(
            SourceIngestionAdmissionStatus.ACTOR_ROLE_NOT_ALLOWED,
        )
    )

    monkeypatch.setattr(dependencies, "get_current_user_id", fake_current_user_id)
    _patch_after_upload_factory(monkeypatch, runner=runner)

    with pytest.raises(HTTPException) as exc_info:
        await knowledge.upload_knowledge(
            project_id="project-1",
            file=_upload_file(),
            preprocessing_mode="faq",
            authorization="Bearer valid-token",
            pool=object(),
            project_repo=_FakeProjectRepo(),
            user_repo=_user_repo(),
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "ACTOR_ROLE_NOT_ALLOWED"


@pytest.mark.asyncio
async def test_upload_rejects_non_utf8_before_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory_called = False

    def fake_make_source_ingestion_first_phase(
        **kwargs: object,
    ) -> _FakeSourceIngestionRunner:
        nonlocal factory_called
        factory_called = True
        return _FakeSourceIngestionRunner(_completed_source_ingestion_result())

    monkeypatch.setattr(
        knowledge,
        "make_knowledge_extraction_workflow_after_upload",
        fake_make_source_ingestion_first_phase,
    )

    with pytest.raises(HTTPException) as exc_info:
        await knowledge.upload_knowledge(
            project_id="project-1",
            file=_upload_file(file_name="binary.pdf", content=b"\xff\xfe"),
            preprocessing_mode="faq",
            authorization="Bearer valid-token",
            pool=object(),
            project_repo=_FakeProjectRepo(),
            user_repo=_user_repo(),
        )

    assert exc_info.value.status_code == 400
    assert (
        exc_info.value.detail
        == "Knowledge upload must be UTF-8 text for source ingestion v1"
    )
    assert factory_called is False


@pytest.mark.asyncio
async def test_upload_rejects_empty_text_before_factory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory_called = False

    def fake_make_source_ingestion_first_phase(
        **kwargs: object,
    ) -> _FakeSourceIngestionRunner:
        nonlocal factory_called
        factory_called = True
        return _FakeSourceIngestionRunner(_completed_source_ingestion_result())

    monkeypatch.setattr(
        knowledge,
        "make_knowledge_extraction_workflow_after_upload",
        fake_make_source_ingestion_first_phase,
    )

    with pytest.raises(HTTPException) as exc_info:
        await knowledge.upload_knowledge(
            project_id="project-1",
            file=_upload_file(file_name="empty.txt", content=b" \n\t"),
            preprocessing_mode="faq",
            authorization="Bearer valid-token",
            pool=object(),
            project_repo=_FakeProjectRepo(),
            user_repo=_user_repo(),
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Knowledge upload text is empty"
    assert factory_called is False


@pytest.mark.asyncio
async def test_upload_missing_token_uses_shared_auth_contract() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await knowledge._require_project_access(
            project_id="project-1",
            authorization=None,
            project_repo=_FakeProjectRepo(),
            user_repo=_user_repo(),
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Authorization header required"


@pytest.mark.asyncio
async def test_upload_invalid_token_uses_shared_auth_contract() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await knowledge._require_project_access(
            project_id="project-1",
            authorization="Bearer wrong-token",
            project_repo=_FakeProjectRepo(),
            user_repo=_user_repo(),
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid token"


@pytest.mark.asyncio
async def test_upload_authorized_via_project_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_current_user_id(authorization: str | None) -> str:
        return "user-1"

    monkeypatch.setattr(dependencies, "get_current_user_id", fake_current_user_id)

    await knowledge._require_project_access(
        project_id="project-1",
        authorization="Bearer valid-token",
        project_repo=_FakeProjectRepo(has_role=True),
        user_repo=_user_repo(platform_admin=False),
    )


@pytest.mark.asyncio
async def test_upload_authorized_via_platform_admin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_current_user_id(authorization: str | None) -> str:
        return "admin-1"

    monkeypatch.setattr(dependencies, "get_current_user_id", fake_current_user_id)

    await knowledge._require_project_access(
        project_id="project-1",
        authorization="Bearer valid-token",
        project_repo=_FakeProjectRepo(has_role=False),
        user_repo=_user_repo(platform_admin=True),
    )


@pytest.mark.asyncio
async def test_upload_forbidden_for_non_owner_non_admin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_current_user_id(authorization: str | None) -> str:
        return "user-1"

    monkeypatch.setattr(dependencies, "get_current_user_id", fake_current_user_id)

    with pytest.raises(HTTPException) as exc_info:
        await knowledge._require_project_access(
            project_id="project-1",
            authorization="Bearer valid-token",
            project_repo=_FakeProjectRepo(has_role=False),
            user_repo=_user_repo(platform_admin=False),
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Insufficient permissions"


@pytest.mark.asyncio
async def test_upload_project_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_current_user_id(authorization: str | None) -> str:
        return "user-1"

    monkeypatch.setattr(dependencies, "get_current_user_id", fake_current_user_id)

    with pytest.raises(HTTPException) as exc_info:
        await knowledge._require_project_access(
            project_id="missing-project",
            authorization="Bearer valid-token",
            project_repo=_FakeProjectRepo(exists=False),
            user_repo=_user_repo(),
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Project not found"


def test_upload_rejects_unsupported_file_type() -> None:
    with pytest.raises(HTTPException) as exc_info:
        knowledge._validate_workbench_upload_file_name("test.exe")

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Unsupported file type: test.exe"


def test_upload_accepts_supported_workbench_source_file_types() -> None:
    for file_name in (
        "faq.txt",
        "faq.md",
        "faq.markdown",
        "faq.pdf",
        "faq.json",
        None,
        "",
        "upload",
    ):
        knowledge._validate_workbench_upload_file_name(file_name)


@pytest.mark.asyncio
async def test_upload_rejects_oversized_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(knowledge.settings, "KNOWLEDGE_UPLOAD_MAX_BYTES", 3)
    monkeypatch.setattr(knowledge.settings, "KNOWLEDGE_UPLOAD_READ_CHUNK_BYTES", 2)

    with pytest.raises(HTTPException) as exc_info:
        await knowledge._read_upload_bytes(_upload_file(content=b"abcd"))

    assert exc_info.value.status_code == 413
    assert exc_info.value.detail == knowledge.UPLOAD_TOO_LARGE_DETAIL


@pytest.mark.asyncio
async def test_upload_file_read_error_maps_to_http_400(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BrokenUpload:
        filename = "broken.md"

        async def read(self, size: int = -1) -> bytes:
            raise RuntimeError("read error")

    with pytest.raises(HTTPException) as exc_info:
        try:
            await knowledge._read_upload_bytes(cast(UploadFile, BrokenUpload()))
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Could not read file") from exc

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Could not read file"


@pytest.mark.asyncio
async def test_non_faq_upload_modes_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_current_user_id(authorization: str | None) -> str:
        return "user-1"

    monkeypatch.setattr(dependencies, "get_current_user_id", fake_current_user_id)

    with pytest.raises(HTTPException) as exc_info:
        await knowledge.upload_knowledge(
            project_id="project-1",
            file=_upload_file(file_name="legacy.txt"),
            preprocessing_mode="plain",
            authorization="Bearer valid-token",
            pool=object(),
            project_repo=_FakeProjectRepo(),
            user_repo=_user_repo(),
        )

    assert exc_info.value.status_code == 400
    assert "Only FAQ Workbench uploads are supported" in str(exc_info.value.detail)


def test_upload_boundary_has_no_legacy_patch_points() -> None:
    source = _source()

    assert not hasattr(knowledge, "ChunkerService")
    assert not hasattr(knowledge, "jwt")

    required = (
        "make_knowledge_extraction_workflow_after_upload",
        "RunSourceIngestionFirstPhaseCommand",
        "_decode_workbench_upload_text",
        "_build_source_ingestion_actor",
        "SourceIngestionActor",
        "_source_units_url",
        "source_units_url",
        "source-units",
    )
    forbidden = (
        "src.interfaces.composition.knowledge_upload",
        "upload_knowledge_file",
        "upload_faq_workbench_knowledge_file",
        "KnowledgeService(",
        "process_knowledge_upload",
        "TASK_PROCESS_KNOWLEDGE_UPLOAD",
    )

    for marker in required:
        assert marker in source

    for marker in forbidden:
        assert marker not in source


def test_clear_knowledge_uses_workbench_clear_composition() -> None:
    source = _source()

    assert "clear_workbench_project" in source
    assert "src.interfaces.composition.faq_workbench_clear" in source
    assert "clear_project_knowledge(" not in source


def test_usage_endpoint_uses_model_usage_read_side_without_knowledge_service() -> None:
    source = _source()

    assert source.count('@router.get("/usage")') == 1
    assert "ModelUsageRepository" in source
    assert "ModelUsageSummaryDto" in source
    assert "KnowledgeService(" not in source


@pytest.mark.asyncio
async def test_unknown_upload_mode_also_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_current_user_id(authorization: str | None) -> str:
        return "user-1"

    monkeypatch.setattr(dependencies, "get_current_user_id", fake_current_user_id)

    with pytest.raises(HTTPException) as exc_info:
        await knowledge.upload_knowledge(
            project_id="project-1",
            file=_upload_file(file_name="legacy.txt"),
            preprocessing_mode="instruction",
            authorization="Bearer valid-token",
            pool=object(),
            project_repo=_FakeProjectRepo(),
            user_repo=_user_repo(),
        )

    assert exc_info.value.status_code == 400
    assert "Only FAQ Workbench uploads are supported" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_source_ingestion_source_units_lists_persisted_units(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_current_user_id(authorization: str | None) -> str:
        assert authorization == "Bearer valid-token"
        return "user-1"

    first_text = "# Alpha\n\nShort source unit"
    second_text = "# Alpha / Huge\n\nFragment"
    repository = _FakeSourceManagementRepository(
        (
            _source_unit(
                unit_ref="source-document:project-1:abc.unit.0",
                ordinal=0,
                unit_kind=SourceUnitKind.SECTION,
                heading_path=("Alpha",),
                text=first_text,
            ),
            _source_unit(
                unit_ref="source-document:project-1:abc.unit.1",
                ordinal=1,
                unit_kind=SourceUnitKind.SPLIT_FRAGMENT,
                heading_path=("Alpha", "Huge"),
                text=second_text,
            ),
        )
    )

    def fake_repository_factory(pool: object) -> _FakeSourceManagementRepository:
        assert pool == "pool"
        return repository

    monkeypatch.setattr(dependencies, "get_current_user_id", fake_current_user_id)
    monkeypatch.setattr(
        knowledge,
        "PostgresSourceManagementRepository",
        fake_repository_factory,
    )

    response = await knowledge.source_ingestion_source_units(
        project_id="project-1",
        source_document_ref="source-document:project-1:abc",
        authorization="Bearer valid-token",
        pool="pool",
        project_repo=_FakeProjectRepo(),
        user_repo=_user_repo(),
    )

    assert response["project_id"] == "project-1"
    assert response["source_document_ref"] == "source-document:project-1:abc"
    assert response["source_unit_count"] == 2

    source_units = response["source_units"]
    assert isinstance(source_units, list)
    assert source_units[0]["source_unit_ref"] == (
        "source-document:project-1:abc.unit.0"
    )
    assert source_units[0]["ordinal"] == 0
    assert source_units[0]["unit_kind"] == "SECTION"
    assert source_units[0]["heading_path"] == ["Alpha"]
    assert source_units[0]["text_preview"] == first_text
    assert source_units[0]["text_length"] == len(first_text)
    assert source_units[0]["created_at"] == "2026-06-10T12:00:00+00:00"
    assert "text" not in source_units[0]

    assert source_units[1]["unit_kind"] == "SPLIT_FRAGMENT"
    assert source_units[1]["heading_path"] == ["Alpha", "Huge"]
    assert repository.document_refs == [
        SourceDocumentRef("source-document:project-1:abc")
    ]


@pytest.mark.asyncio
async def test_source_ingestion_source_units_empty_list_returns_200(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_current_user_id(authorization: str | None) -> str:
        return "user-1"

    repository = _FakeSourceManagementRepository(())

    def fake_repository_factory(pool: object) -> _FakeSourceManagementRepository:
        return repository

    monkeypatch.setattr(dependencies, "get_current_user_id", fake_current_user_id)
    monkeypatch.setattr(
        knowledge,
        "PostgresSourceManagementRepository",
        fake_repository_factory,
    )

    response = await knowledge.source_ingestion_source_units(
        project_id="project-1",
        source_document_ref="source-document:project-1:abc",
        authorization="Bearer valid-token",
        pool=object(),
        project_repo=_FakeProjectRepo(),
        user_repo=_user_repo(),
    )

    assert response == {
        "project_id": "project-1",
        "source_document_ref": "source-document:project-1:abc",
        "source_unit_count": 0,
        "source_units": [],
    }


@pytest.mark.asyncio
async def test_source_ingestion_source_units_requires_project_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_current_user_id(authorization: str | None) -> str:
        return "user-1"

    repository_factory_called = False

    def fake_repository_factory(pool: object) -> _FakeSourceManagementRepository:
        nonlocal repository_factory_called
        repository_factory_called = True
        return _FakeSourceManagementRepository(())

    monkeypatch.setattr(dependencies, "get_current_user_id", fake_current_user_id)
    monkeypatch.setattr(
        knowledge,
        "PostgresSourceManagementRepository",
        fake_repository_factory,
    )

    with pytest.raises(HTTPException) as exc_info:
        await knowledge.source_ingestion_source_units(
            project_id="project-1",
            source_document_ref="source-document:project-1:abc",
            authorization="Bearer valid-token",
            pool=object(),
            project_repo=_FakeProjectRepo(has_role=False),
            user_repo=_user_repo(platform_admin=False),
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Insufficient permissions"
    assert repository_factory_called is False


@pytest.mark.asyncio
async def test_source_ingestion_source_units_preview_is_capped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_current_user_id(authorization: str | None) -> str:
        return "user-1"

    long_text = "x" * 600
    repository = _FakeSourceManagementRepository(
        (
            _source_unit(
                unit_ref="source-document:project-1:abc.unit.0",
                ordinal=0,
                unit_kind=SourceUnitKind.SECTION,
                heading_path=("Alpha",),
                text=long_text,
            ),
        )
    )

    def fake_repository_factory(pool: object) -> _FakeSourceManagementRepository:
        return repository

    monkeypatch.setattr(dependencies, "get_current_user_id", fake_current_user_id)
    monkeypatch.setattr(
        knowledge,
        "PostgresSourceManagementRepository",
        fake_repository_factory,
    )

    response = await knowledge.source_ingestion_source_units(
        project_id="project-1",
        source_document_ref="source-document:project-1:abc",
        authorization="Bearer valid-token",
        pool=object(),
        project_repo=_FakeProjectRepo(),
        user_repo=_user_repo(),
    )

    source_units = response["source_units"]
    assert isinstance(source_units, list)
    preview = source_units[0]["text_preview"]
    assert isinstance(preview, str)
    assert len(preview) == 500
    assert source_units[0]["text_length"] == 600
    assert "text" not in source_units[0]


def test_source_ingestion_source_units_read_side_guard() -> None:
    source = _source()
    route_marker = '@router.get("/source-documents/{source_document_ref}/source-units")'
    assert route_marker in source
    endpoint_region = source.split(route_marker, 1)[1].split(
        '@router.get("/{document_id}/progress")',
        1,
    )[0]

    endpoint_required = (
        "SourceDocumentRef",
        "list_source_units_for_document",
        "_source_unit_read_model",
    )
    source_required = (
        "source-units",
        "text_preview",
        "text_length",
    )
    forbidden = (
        "RunClaimExtractionStageAsync",
        "CLAIM_BUILDER_WORK_SCHEDULED",
        "capacity_runtime",
        "execution_runtime",
        "llm_runtime",
        "artifact_runtime",
        "worker_loop",
        "JobDispatcher",
        "queue",
        "openpyxl",
        "pandas",
        "BeautifulSoup",
    )

    for marker in endpoint_required:
        assert marker in endpoint_region

    for marker in source_required:
        assert marker in source

    for marker in forbidden:
        assert marker not in endpoint_region


def test_upload_response_source_units_url_source_guard() -> None:
    source = _source()

    upload_region = source.split('@router.post("")', 1)[1].split(
        '@router.get("/source-documents/{source_document_ref}/source-units")',
        1,
    )[0]
    source_units_region = source.split(
        '@router.get("/source-documents/{source_document_ref}/source-units")',
        1,
    )[1].split('@router.get("/usage")', 1)[0]
    checked_region = upload_region + source_units_region

    required = (
        "_source_units_url",
        "source_units_url",
        "source-units",
    )
    forbidden = (
        "RunClaimExtractionStageAsync",
        "CLAIM_BUILDER_WORK_SCHEDULED",
        "capacity_runtime",
        "execution_runtime",
        "llm_runtime",
        "artifact_runtime",
        "worker_loop",
        "JobDispatcher",
        "queue",
        "openpyxl",
        "pandas",
        "BeautifulSoup",
    )

    for marker in required:
        assert marker in source

    for marker in forbidden:
        assert marker not in checked_region


def test_knowledge_http_routes_are_not_duplicated() -> None:
    source = _source()

    duplicated_route_markers = (
        '@router.get("/usage")',
        '@router.get("/{document_id}/price-facts")',
        '@router.get("/commercial-truth-review")',
        '@router.get("/{document_id}/commercial-truth-review")',
        '@router.post("/{document_id}/price-facts/publish")',
        '@router.post("/{document_id}/price-facts/reject")',
    )

    for marker in duplicated_route_markers:
        assert source.count(marker) == 1

    assert "_source_units_url" in source
    assert (
        '@router.get("/source-documents/{source_document_ref}/source-units")' in source
    )
    assert "source_units_url" in source

    guarded_region = source.split('@router.post("")', 1)[1].split(
        '@router.post("/{document_id}/retighten")',
        1,
    )[0]
    forbidden = (
        "RunClaimExtractionStageAsync",
        "CLAIM_BUILDER_WORK_SCHEDULED",
        "capacity_runtime",
        "execution_runtime",
        "llm_runtime",
        "artifact_runtime",
        "worker_loop",
        "JobDispatcher",
        "queue",
    )

    for marker in forbidden:
        assert marker not in guarded_region


@pytest.mark.asyncio
async def test_source_document_draft_claims_endpoint_requires_project_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_current_user_id(authorization: str | None) -> str:
        return "user-1"

    monkeypatch.setattr(dependencies, "get_current_user_id", fake_current_user_id)
    monkeypatch.setattr(
        knowledge,
        "PostgresDraftClaimObservationReadRepository",
        _FakeDraftClaimObservationReadRepository,
    )
    _FakeDraftClaimObservationReadRepository.instances = []
    _FakeDraftClaimObservationReadRepository.configured_items = ()

    with pytest.raises(HTTPException) as exc_info:
        await knowledge.source_document_draft_claims(
            project_id="project-1",
            source_document_ref="source-document:project-1:abc",
            authorization="Bearer valid-token",
            limit=50,
            offset=0,
            pool=object(),
            project_repo=_FakeProjectRepo(has_role=False),
            user_repo=_user_repo(platform_admin=False),
        )

    assert exc_info.value.status_code == 403
    assert _FakeDraftClaimObservationReadRepository.instances == []


@pytest.mark.asyncio
async def test_source_document_draft_claims_endpoint_returns_empty_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_current_user_id(authorization: str | None) -> str:
        return "user-1"

    monkeypatch.setattr(dependencies, "get_current_user_id", fake_current_user_id)
    monkeypatch.setattr(
        knowledge,
        "PostgresDraftClaimObservationReadRepository",
        _FakeDraftClaimObservationReadRepository,
    )
    _FakeDraftClaimObservationReadRepository.instances = []
    _FakeDraftClaimObservationReadRepository.configured_items = ()

    response = await knowledge.source_document_draft_claims(
        project_id="project-1",
        source_document_ref="source-document:project-1:abc",
        authorization="Bearer valid-token",
        limit=50,
        offset=0,
        pool=object(),
        project_repo=_FakeProjectRepo(has_role=True),
        user_repo=_user_repo(),
    )

    assert response == {
        "source_document_ref": "source-document:project-1:abc",
        "count": 0,
        "limit": 50,
        "offset": 0,
        "items": [],
    }


@pytest.mark.asyncio
async def test_source_document_draft_claims_endpoint_returns_persisted_claims(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_current_user_id(authorization: str | None) -> str:
        return "user-1"

    item = _draft_claim_read_model()
    monkeypatch.setattr(dependencies, "get_current_user_id", fake_current_user_id)
    monkeypatch.setattr(
        knowledge,
        "PostgresDraftClaimObservationReadRepository",
        _FakeDraftClaimObservationReadRepository,
    )
    _FakeDraftClaimObservationReadRepository.instances = []
    _FakeDraftClaimObservationReadRepository.configured_items = (item,)

    response = await knowledge.source_document_draft_claims(
        project_id="project-1",
        source_document_ref="source-document:project-1:abc",
        authorization="Bearer valid-token",
        limit=50,
        offset=0,
        pool=object(),
        project_repo=_FakeProjectRepo(has_role=True),
        user_repo=_user_repo(),
    )

    assert response["count"] == 1
    assert response["limit"] == 50
    assert response["offset"] == 0
    assert response["items"] == [
        {
            "observation_ref": item.observation_ref,
            "source_unit_ref": item.source_unit_ref,
            "claim": item.claim,
            "granularity": item.granularity,
            "possible_questions": ["What does the system do?"],
            "exclusion_scope": "",
            "evidence_block": item.evidence_block,
            "provenance": {
                "workflow_run_id": "workflow-1",
                "stage_run_id": "claim_builder_section_extraction",
                "work_item_id": "work-1",
                "work_item_attempt_id": "work-1:attempt-1",
                "llm_task_id": "work-1",
                "llm_attempt_id": "work-1:attempt-1",
                "prompt_id": "faq_claim_observations",
                "prompt_version": "v1",
                "claim_index": 0,
            },
            "created_at": "2026-06-13T12:00:00+00:00",
        }
    ]


@pytest.mark.asyncio
async def test_source_unit_draft_claims_endpoint_returns_only_selected_unit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_current_user_id(authorization: str | None) -> str:
        return "user-1"

    monkeypatch.setattr(dependencies, "get_current_user_id", fake_current_user_id)
    monkeypatch.setattr(
        knowledge,
        "PostgresDraftClaimObservationReadRepository",
        _FakeDraftClaimObservationReadRepository,
    )
    _FakeDraftClaimObservationReadRepository.instances = []
    _FakeDraftClaimObservationReadRepository.configured_items = (
        _draft_claim_read_model(
            observation_ref="draft-claim-observation:1",
            source_unit_ref="source-unit:1",
            claim_index=0,
        ),
        _draft_claim_read_model(
            observation_ref="draft-claim-observation:2",
            source_unit_ref="source-unit:2",
            claim_index=1,
        ),
    )

    response = await knowledge.source_unit_draft_claims(
        project_id="project-1",
        source_unit_ref="source-unit:2",
        authorization="Bearer valid-token",
        limit=50,
        offset=0,
        pool=object(),
        project_repo=_FakeProjectRepo(has_role=True),
        user_repo=_user_repo(),
    )

    assert response["source_unit_ref"] == "source-unit:2"
    assert response["count"] == 1
    assert response["items"][0]["observation_ref"] == "draft-claim-observation:2"


@pytest.mark.asyncio
async def test_draft_claims_endpoint_respects_limit_and_offset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_current_user_id(authorization: str | None) -> str:
        return "user-1"

    monkeypatch.setattr(dependencies, "get_current_user_id", fake_current_user_id)
    monkeypatch.setattr(
        knowledge,
        "PostgresDraftClaimObservationReadRepository",
        _FakeDraftClaimObservationReadRepository,
    )
    _FakeDraftClaimObservationReadRepository.instances = []
    _FakeDraftClaimObservationReadRepository.configured_items = (
        _draft_claim_read_model(observation_ref="draft-claim-observation:1"),
        _draft_claim_read_model(observation_ref="draft-claim-observation:2"),
    )

    response = await knowledge.source_document_draft_claims(
        project_id="project-1",
        source_document_ref="source-document:project-1:abc",
        authorization="Bearer valid-token",
        limit=1,
        offset=1,
        pool=object(),
        project_repo=_FakeProjectRepo(has_role=True),
        user_repo=_user_repo(),
    )

    repository = _FakeDraftClaimObservationReadRepository.instances[0]
    assert repository.document_calls == [
        {
            "source_document_ref": "source-document:project-1:abc",
            "limit": 1,
            "offset": 1,
        }
    ]
    assert response["count"] == 1
    assert response["items"][0]["observation_ref"] == "draft-claim-observation:2"
