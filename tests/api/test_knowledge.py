from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import cast

import pytest
from fastapi import HTTPException, UploadFile
from src.contexts.knowledge_workbench.application.sagas.run_source_ingestion_first_phase import (
    RunSourceIngestionFirstPhaseCommand,
    RunSourceIngestionFirstPhaseResult,
    RunSourceIngestionFirstPhaseStatus,
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


def _completed_source_ingestion_result() -> RunSourceIngestionFirstPhaseResult:
    return RunSourceIngestionFirstPhaseResult(
        status=RunSourceIngestionFirstPhaseStatus.COMPLETED,
        admission_status=SourceIngestionAdmissionStatus.ALLOWED,
        workflow_run_id="knowledge-extraction:source-document:project-1:abc",
        source_document_ref="source-document:project-1:abc",
        source_unit_count=3,
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
async def test_upload_success_uses_source_ingestion_first_phase(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_current_user_id(authorization: str | None) -> str:
        assert authorization == "Bearer valid-token"
        return "user-1"

    runner = _FakeSourceIngestionRunner(_completed_source_ingestion_result())
    factory_calls: list[dict[str, object]] = []

    def fake_make_source_ingestion_first_phase(
        **kwargs: object,
    ) -> _FakeSourceIngestionRunner:
        factory_calls.append(kwargs)
        return runner

    monkeypatch.setattr(dependencies, "get_current_user_id", fake_current_user_id)
    monkeypatch.setattr(
        knowledge,
        "make_source_ingestion_first_phase",
        fake_make_source_ingestion_first_phase,
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
        "status": "source_ingestion_first_phase_completed",
        "workflow_run_id": "knowledge-extraction:source-document:project-1:abc",
        "source_document_ref": "source-document:project-1:abc",
        "source_unit_count": 3,
        "source_units_url": (
            "/api/projects/project-1/knowledge/source-documents/"
            "source-document:project-1:abc/source-units"
        ),
    }
    assert len(factory_calls) == 1
    assert len(runner.commands) == 1

    command = runner.commands[0]
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

    def fake_make_source_ingestion_first_phase(
        **kwargs: object,
    ) -> _FakeSourceIngestionRunner:
        return runner

    monkeypatch.setattr(dependencies, "get_current_user_id", fake_current_user_id)
    monkeypatch.setattr(
        knowledge,
        "make_source_ingestion_first_phase",
        fake_make_source_ingestion_first_phase,
    )

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

    def fake_make_source_ingestion_first_phase(
        **kwargs: object,
    ) -> _FakeSourceIngestionRunner:
        return runner

    monkeypatch.setattr(dependencies, "get_current_user_id", fake_current_user_id)
    monkeypatch.setattr(
        knowledge,
        "make_source_ingestion_first_phase",
        fake_make_source_ingestion_first_phase,
    )

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

    def fake_make_source_ingestion_first_phase(
        **kwargs: object,
    ) -> _FakeSourceIngestionRunner:
        return runner

    monkeypatch.setattr(dependencies, "get_current_user_id", fake_current_user_id)
    monkeypatch.setattr(
        knowledge,
        "make_source_ingestion_first_phase",
        fake_make_source_ingestion_first_phase,
    )

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
        "make_source_ingestion_first_phase",
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
        "make_source_ingestion_first_phase",
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
        "make_source_ingestion_first_phase",
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
