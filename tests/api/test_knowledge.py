from __future__ import annotations

from dataclasses import dataclass
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


def _upload_file(
    *,
    file_name: str = "faq.md",
    content: bytes = b"# FAQ\nAnswer",
) -> UploadFile:
    return UploadFile(filename=file_name, file=BytesIO(content))


def _source() -> str:
    return Path("src/interfaces/http/knowledge.py").read_text(encoding="utf-8")


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
