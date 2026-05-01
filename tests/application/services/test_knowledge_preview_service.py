from collections.abc import Sequence
from dataclasses import dataclass

import pytest

from src.application.dto.knowledge_dto import KnowledgePreviewRequestDto
from src.application.services.knowledge_service import KnowledgeService
from src.domain.project_plane.knowledge_views import KnowledgeSearchResultView


@dataclass(frozen=True, slots=True)
class ProjectView:
    user_id: str


class FakeJwt:
    class ExpiredSignatureError(Exception):
        pass

    class InvalidTokenError(Exception):
        pass

    @staticmethod
    def decode(token: str, secret: str, algorithms: list[str]) -> dict[str, str]:
        return {"sub": token}


class FakeProjectRepo:
    async def user_has_project_role(
        self,
        project_id: str,
        user_id: str,
        allowed_roles: Sequence[str],
    ) -> bool:
        return user_id == "owner-user" and "owner" in allowed_roles

    async def get_project_view(self, project_id: str) -> ProjectView | None:
        return ProjectView(user_id="owner-user")

    async def project_exists(self, project_id: str) -> bool:
        return project_id == "project-1"


class FakeUserRepo:
    async def is_platform_admin(self, user_id: str) -> bool:
        return False


class FakeLogger:
    def info(self, message: str, *args: object, **kwargs: object) -> None:
        return None

    def warning(self, message: str, *args: object, **kwargs: object) -> None:
        return None

    def error(self, message: str, *args: object, **kwargs: object) -> None:
        return None

    def exception(self, message: str, *args: object, **kwargs: object) -> None:
        return None


class FakeKnowledgeRepo:
    def __init__(self) -> None:
        self.search_calls: list[tuple[str, str, int, bool]] = []
        self.preview_calls: list[tuple[str, str, int]] = []

    async def create_document(
        self,
        project_id: str,
        file_name: str,
        file_size: int | None = None,
        uploaded_by: str | None = None,
    ) -> str:
        return "doc-1"

    async def add_knowledge_batch(
        self,
        project_id: str,
        chunks: list[dict[str, object]],
        document_id: str | None = None,
    ) -> int:
        return len(chunks)

    async def add_structured_knowledge_batch(
        self,
        project_id: str,
        chunks: list[dict[str, object]],
        document_id: str | None = None,
    ) -> int:
        return len(chunks)

    async def update_document_status(
        self,
        document_id: str,
        status: str,
        error: str | None = None,
    ) -> None:
        return None

    async def update_document_preprocessing_status(
        self,
        document_id: str,
        *,
        mode: str,
        status: str,
        error: str | None = None,
        model: str | None = None,
        prompt_version: str | None = None,
        metrics: dict[str, object] | None = None,
    ) -> None:
        return None

    async def search(
        self,
        project_id: str,
        query: str,
        limit: int = 10,
        hybrid_fallback: bool = True,
    ) -> list[KnowledgeSearchResultView]:
        self.search_calls.append((project_id, query, limit, hybrid_fallback))
        return [
            KnowledgeSearchResultView(
                id="chunk-1",
                content="Р”РѕСЃС‚Р°РІРєР° Р·Р°РЅРёРјР°РµС‚ 2-3 РґРЅСЏ.",
                score=0.82,
                method="hybrid",
                document_id="doc-1",
                source="delivery.md",
                document_status="processed",
            )
        ]

    async def preview_search(
        self,
        project_id: str,
        query: str,
        limit: int = 10,
    ) -> list[KnowledgeSearchResultView]:
        self.preview_calls.append((project_id, query, limit))
        return [
            KnowledgeSearchResultView(
                id="chunk-1",
                content="Доставка занимает 2-3 дня.",
                score=0.82,
                method="hybrid",
                document_id="doc-1",
                source="delivery.md",
                document_status="processed",
            )
        ]

    async def clear_project_knowledge(self, project_id: str) -> None:
        self.preview_calls.append((project_id, "clear", 0))


@pytest.mark.asyncio
async def test_preview_query_uses_existing_search_without_generation() -> None:
    repo = FakeKnowledgeRepo()
    service = KnowledgeService(
        FakeProjectRepo(),
        FakeUserRepo(),
        object(),
        "secret",
        FakeJwt,
    )

    result = await service.preview_query(
        "project-1",
        KnowledgePreviewRequestDto(question="  Сколько идёт доставка?  ", limit=5),
        "Bearer owner-user",
        knowledge_repo_factory=lambda pool: repo,
        logger=FakeLogger(),
    )

    assert repo.preview_calls == [("project-1", "Сколько идёт доставка?", 5)]
    assert repo.search_calls == []
    assert result.best_result is not None
    assert result.best_result.content == "Доставка занимает 2-3 дня."
    assert result.best_result.source == "delivery.md"


@pytest.mark.asyncio
async def test_preview_query_returns_empty_for_blank_question() -> None:
    repo = FakeKnowledgeRepo()
    service = KnowledgeService(
        FakeProjectRepo(),
        FakeUserRepo(),
        object(),
        "secret",
        FakeJwt,
    )

    result = await service.preview_query(
        "project-1",
        KnowledgePreviewRequestDto(question="   ", limit=5),
        "Bearer owner-user",
        knowledge_repo_factory=lambda pool: repo,
        logger=FakeLogger(),
    )

    assert repo.preview_calls == []
    assert repo.search_calls == []
    assert result.is_empty is True
    assert result.best_result is None
    assert result.top_results == []
