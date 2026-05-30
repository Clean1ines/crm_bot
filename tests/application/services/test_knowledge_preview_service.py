from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass

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

    async def search(
        self,
        project_id: str,
        query: str,
        limit: int = 10,
        hybrid_fallback: bool = True,
        thread_id: str | None = None,
    ) -> list[KnowledgeSearchResultView]:
        self.search_calls.append((project_id, query, limit, hybrid_fallback))
        return [
            KnowledgeSearchResultView(
                id="runtime-1",
                content="Доставка занимает 2-3 дня.",
                score=0.82,
                method="retrieval_surface_hybrid",
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
                id="lexical-1",
                content="Лексический debug: доставка 2-3 дня.",
                score=0.72,
                method="retrieval_surface_lexical",
                document_id="doc-1",
                source="delivery.md",
                document_status="processed",
            )
        ]

    async def clear_project_knowledge(self, project_id: str) -> None:
        self.preview_calls.append((project_id, "clear", 0))


def make_service() -> KnowledgeService:
    return KnowledgeService(
        FakeProjectRepo(),
        FakeUserRepo(),
        object(),
        "secret",
        FakeJwt,
    )


def test_preview_query_default_uses_runtime_equivalent_search_not_lexical_preview() -> (
    None
):
    repo = FakeKnowledgeRepo()

    result = asyncio.run(
        make_service().preview_query(
            "project-1",
            KnowledgePreviewRequestDto(question="  сколько идёт доставка?  ", limit=5),
            "Bearer owner-user",
            knowledge_repo_factory=lambda pool: repo,
            logger=FakeLogger(),
        )
    )

    assert repo.search_calls == [("project-1", "сколько идёт доставка?", 10, True)]
    assert repo.preview_calls == []
    assert result.retrieval_mode == "runtime_equivalent"
    assert result.method == "production_runtime_search"
    assert result.trace["runtime_equivalent"] is True
    assert result.trace["production_safe"] is True
    assert result.best_result is not None
    assert result.best_result.id == "runtime-1"


def test_preview_query_lexical_debug_uses_old_preview_search_path() -> None:
    repo = FakeKnowledgeRepo()

    result = asyncio.run(
        make_service().preview_query(
            "project-1",
            KnowledgePreviewRequestDto(
                question="Сколько идёт доставка?",
                limit=5,
                retrieval_mode="lexical_debug",
            ),
            "Bearer owner-user",
            knowledge_repo_factory=lambda pool: repo,
            logger=FakeLogger(),
        )
    )

    assert repo.search_calls == []
    assert repo.preview_calls == [("project-1", "Сколько идёт доставка?", 10)]
    assert result.retrieval_mode == "lexical_debug"
    assert result.method == "lexical_debug_preview_search"
    assert result.trace["diagnostic"] is True
    assert result.trace["runtime_equivalent"] is False
    assert result.best_result is not None
    assert result.best_result.id == "lexical-1"


def test_preview_query_returns_empty_for_blank_question_without_retrieval_call() -> (
    None
):
    repo = FakeKnowledgeRepo()

    result = asyncio.run(
        make_service().preview_query(
            "project-1",
            KnowledgePreviewRequestDto(question="   ", limit=5),
            "Bearer owner-user",
            knowledge_repo_factory=lambda pool: repo,
            logger=FakeLogger(),
        )
    )

    assert repo.preview_calls == []
    assert repo.search_calls == []
    assert result.is_empty is True
    assert result.retrieval_mode == "runtime_equivalent"
    assert result.method == "production_runtime_search"
    assert result.best_result is None
    assert result.top_results == []


def test_preview_dedupes_exact_duplicate_answers_if_duplicate_rows_exist() -> None:
    class DuplicateRuntimeRepo(FakeKnowledgeRepo):
        async def search(
            self,
            project_id: str,
            query: str,
            limit: int = 10,
            hybrid_fallback: bool = True,
            thread_id: str | None = None,
        ) -> list[KnowledgeSearchResultView]:
            self.search_calls.append((project_id, query, limit, hybrid_fallback))
            return [
                KnowledgeSearchResultView(
                    id="chunk-1",
                    content="Доставка занимает 2-3 дня.",
                    score=0.90,
                    method="retrieval_surface_hybrid",
                ),
                KnowledgeSearchResultView(
                    id="chunk-2",
                    content="Доставка занимает 2-3 дня.",
                    score=0.80,
                    method="retrieval_surface_hybrid",
                ),
            ]

    repo = DuplicateRuntimeRepo()

    result = asyncio.run(
        make_service().preview_query(
            "project-1",
            KnowledgePreviewRequestDto(question="Сколько идёт доставка?", limit=5),
            "Bearer owner-user",
            knowledge_repo_factory=lambda pool: repo,
            logger=FakeLogger(),
        )
    )

    assert repo.preview_calls == []
    assert len(result.top_results) == 1
    assert result.top_results[0].id == "chunk-1"
