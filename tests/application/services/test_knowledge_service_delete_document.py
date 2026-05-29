from __future__ import annotations

from dataclasses import dataclass
import pytest

from src.application.errors import NotFoundError
from src.application.services.knowledge_service import KnowledgeService


@dataclass(frozen=True)
class FakeDocument:
    id: str
    project_id: str
    file_name: str = "knowledge.md"


class FakeJwt:
    class ExpiredSignatureError(Exception):
        pass

    class InvalidTokenError(Exception):
        pass

    def decode(
        self,
        token: str,
        secret: str,
        algorithms: list[str],
    ) -> dict[str, str]:
        assert token == "token"
        assert secret == "secret"
        assert algorithms == ["HS256"]
        return {"sub": "user-1"}


class FakeProjectRepo:
    async def project_exists(self, project_id: str) -> bool:
        return project_id == "project-1"

    async def user_has_project_role(
        self,
        project_id: str,
        user_id: str,
        roles: list[str],
    ) -> bool:
        return project_id == "project-1" and user_id == "user-1" and "admin" in roles

    async def get_project_view(self, project_id: str) -> object | None:
        return None


class FakeUserRepo:
    async def is_platform_admin(self, user_id: str) -> bool:
        return False


class FakeKnowledgeRepo:
    def __init__(self, document: FakeDocument | None) -> None:
        self.document = document
        self.deleted_document_ids: list[str] = []

    async def get_document(self, document_id: str) -> FakeDocument | None:
        if self.document is not None and self.document.id == document_id:
            return self.document
        return None

    async def delete_document(self, document_id: str) -> None:
        self.deleted_document_ids.append(document_id)


class FakeLogger:
    def info(self, *args: object, **kwargs: object) -> None:
        pass

    def warning(self, *args: object, **kwargs: object) -> None:
        pass

    def error(self, *args: object, **kwargs: object) -> None:
        pass

    def exception(self, *args: object, **kwargs: object) -> None:
        pass


def make_service() -> KnowledgeService:
    return KnowledgeService(
        FakeProjectRepo(),
        FakeUserRepo(),
        pool=object(),
        jwt_secret="secret",
        jwt_module=FakeJwt(),
    )


@pytest.mark.asyncio
async def test_delete_document_deletes_existing_project_document() -> None:
    service = make_service()
    repo = FakeKnowledgeRepo(FakeDocument(id="doc-1", project_id="project-1"))

    await service.delete_document(
        "project-1",
        "doc-1",
        "Bearer token",
        knowledge_repo_factory=lambda _pool: repo,
        logger=FakeLogger(),
    )

    assert repo.deleted_document_ids == ["doc-1"]


@pytest.mark.asyncio
async def test_delete_document_denies_missing_document() -> None:
    service = make_service()
    repo = FakeKnowledgeRepo(None)

    with pytest.raises(NotFoundError):
        await service.delete_document(
            "project-1",
            "missing-doc",
            "Bearer token",
            knowledge_repo_factory=lambda _pool: repo,
            logger=FakeLogger(),
        )

    assert repo.deleted_document_ids == []


@pytest.mark.asyncio
async def test_delete_document_denies_foreign_document() -> None:
    service = make_service()
    repo = FakeKnowledgeRepo(FakeDocument(id="doc-1", project_id="project-2"))

    with pytest.raises(NotFoundError):
        await service.delete_document(
            "project-1",
            "doc-1",
            "Bearer token",
            knowledge_repo_factory=lambda _pool: repo,
            logger=FakeLogger(),
        )

    assert repo.deleted_document_ids == []
