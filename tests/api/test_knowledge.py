from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import pytest
from fastapi import HTTPException
from starlette.datastructures import UploadFile

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


class _Result:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def to_dict(self) -> dict[str, object]:
        return self._payload


def _upload_file(
    *,
    file_name: str = "faq.md",
    content: bytes = b"# FAQ\nAnswer",
) -> UploadFile:
    return UploadFile(filename=file_name, file=BytesIO(content))


def _source() -> str:
    return Path("src/interfaces/http/knowledge.py").read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_upload_success_uses_workbench_upload_composition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_current_user_id(authorization: str | None) -> str:
        assert authorization == "Bearer valid-token"
        return "user-1"

    calls: dict[str, object] = {}

    async def fake_workbench_upload(**kwargs: object) -> _Result:
        calls.update(kwargs)
        return _Result(
            {
                "document_id": "document-1",
                "status": "queued",
                "preprocessing_mode": "faq",
            }
        )

    import src.interfaces.composition.faq_workbench_upload as upload_composition

    monkeypatch.setattr(dependencies, "get_current_user_id", fake_current_user_id)
    monkeypatch.setattr(
        upload_composition,
        "upload_faq_workbench_knowledge_file",
        fake_workbench_upload,
    )

    response = await knowledge.upload_knowledge(
        project_id="project-1",
        file=_upload_file(),
        preprocessing_mode="faq",
        authorization="Bearer valid-token",
        pool=object(),
        project_repo=_FakeProjectRepo(),
        queue_repo=object(),
        user_repo=_FakeUserRepo(),
    )

    assert response == {
        "document_id": "document-1",
        "status": "queued",
        "preprocessing_mode": "faq",
    }
    assert calls["project_id"] == "project-1"
    assert calls["file_name"] == "faq.md"
    assert calls["file_content"] == b"# FAQ\nAnswer"


@pytest.mark.asyncio
async def test_upload_missing_token_uses_shared_auth_contract() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await knowledge._require_project_access(
            project_id="project-1",
            authorization=None,
            project_repo=_FakeProjectRepo(),
            user_repo=_FakeUserRepo(),
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
            user_repo=_FakeUserRepo(),
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
        user_repo=_FakeUserRepo(platform_admin=False),
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
        user_repo=_FakeUserRepo(platform_admin=True),
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
            user_repo=_FakeUserRepo(platform_admin=False),
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
            user_repo=_FakeUserRepo(),
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
            await knowledge._read_upload_bytes(BrokenUpload())
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
            queue_repo=object(),
            user_repo=_FakeUserRepo(),
        )

    assert exc_info.value.status_code == 400
    assert "Only FAQ Workbench uploads are supported" in str(exc_info.value.detail)


def test_upload_boundary_has_no_legacy_patch_points() -> None:
    source = _source()

    assert not hasattr(knowledge, "ChunkerService")
    assert not hasattr(knowledge, "jwt")

    forbidden = (
        "src.interfaces.composition.knowledge_upload",
        "upload_knowledge_file",
        "KnowledgeService(",
        "process_knowledge_upload",
        "TASK_PROCESS_KNOWLEDGE_UPLOAD",
    )
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
            queue_repo=object(),
            user_repo=_FakeUserRepo(),
        )

    assert exc_info.value.status_code == 400
    assert "Only FAQ Workbench uploads are supported" in str(exc_info.value.detail)
