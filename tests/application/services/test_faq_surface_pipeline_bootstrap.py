from __future__ import annotations

from dataclasses import dataclass

import pytest

from src.application.services.knowledge_ingestion_service import KnowledgeIngestionService
from src.domain.project_plane.knowledge_preprocessing import MODE_FAQ


@dataclass
class _CallState:
    surface_runs: int = 0
    surface_stages: int = 0
    surface_source_units: int = 0
    surfaces: int = 0
    relations: int = 0
    ownership: int = 0
    document_status_updates: int = 0
    preprocessing_updates: int = 0


class _FakeRepo:
    def __init__(self) -> None:
        self.calls = _CallState()

    async def delete_document_chunks(self, document_id: str) -> None:  # noqa: ARG002
        return

    async def create_compiler_run(self, run) -> None:  # noqa: ANN001
        return

    async def add_source_chunks(self, *, project_id: str, document_id: str, chunks) -> None:  # noqa: ANN001, ARG002
        return

    async def create_surface_compiler_run(self, run) -> None:  # noqa: ANN001
        self.calls.surface_runs += 1

    async def create_surface_compiler_stage(self, stage) -> None:  # noqa: ANN001
        self.calls.surface_stages += 1

    async def save_surface_source_units(self, *, run_id: str, document_id: str, source_units) -> None:  # noqa: ANN001, ARG002
        if source_units:
            self.calls.surface_source_units += len(source_units)

    async def update_surface_compiler_run_status(self, *, run_id: str, status: str, error_type=None, error_message=None) -> None:  # noqa: ANN001, ARG002
        return

    async def save_surfaces(self, *, run_id: str, document_id: str, surfaces) -> None:  # noqa: ANN001, ARG002
        self.calls.surfaces += len(surfaces)

    async def save_surface_relations(self, *, run_id: str, document_id: str, relations) -> None:  # noqa: ANN001, ARG002
        self.calls.relations += len(relations)

    async def save_surface_question_ownership(self, *, run_id: str, document_id: str, ownership) -> None:  # noqa: ANN001, ARG002
        self.calls.ownership += len(ownership)

    async def save_surface_question_reassignments(self, *, run_id: str, document_id: str, reassignments) -> None:  # noqa: ANN001, ARG002
        return

    async def save_surface_merge_decisions(self, *, run_id: str, document_id: str, merge_decisions) -> None:  # noqa: ANN001, ARG002
        return

    async def update_document_preprocessing_status(self, document_id: str, **kwargs) -> None:  # noqa: ANN001, ARG002
        self.calls.preprocessing_updates += 1

    async def update_document_status(self, document_id: str, status: str, detail: str | None = None) -> None:  # noqa: ARG002
        self.calls.document_status_updates += 1


class _FakeUsageRepo:
    pass


@pytest.mark.asyncio
async def test_process_document_routes_faq_into_surface_bootstrap_flow() -> None:
    repo = _FakeRepo()
    service = KnowledgeIngestionService(pool=None)

    result = await service.process_document(
        project_id="00000000-0000-0000-0000-000000000001",
        document_id="00000000-0000-0000-0000-000000000002",
        file_name="faq.md",
        chunks=[{"content": "Что умеет продукт", "title": "О продукте"}],
        mode=MODE_FAQ,
        knowledge_repo_factory=lambda _pool: repo,
        model_usage_repo_factory=lambda _pool: _FakeUsageRepo(),
        preprocessor_factory=lambda: object(),
        logger=None,  # not used in FAQ bootstrap path
    )

    assert result.preprocessing_status == "completed"
    assert repo.calls.surface_runs == 1
    assert repo.calls.surface_stages == 2
    assert repo.calls.surface_source_units == 1
    assert repo.calls.preprocessing_updates == 1
    assert repo.calls.document_status_updates == 1
    assert repo.calls.surfaces == 1
    assert repo.calls.ownership == 1
