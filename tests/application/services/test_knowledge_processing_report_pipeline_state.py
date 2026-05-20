from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.application.services.knowledge_service import KnowledgeService


class FakeJwt:
    class ExpiredSignatureError(Exception):
        pass

    class InvalidTokenError(Exception):
        pass

    @staticmethod
    def decode(token, secret, algorithms):
        return {"sub": "user-1"}


@pytest.fixture
def service() -> KnowledgeService:
    project_repo = Mock()
    project_repo.user_has_project_role = AsyncMock(return_value=True)
    project_repo.project_exists = AsyncMock(return_value=True)

    user_repo = Mock()
    user_repo.is_platform_admin = AsyncMock(return_value=False)

    return KnowledgeService(project_repo, user_repo, object(), "secret", FakeJwt)


def _document(**overrides: object) -> SimpleNamespace:
    payload = {
        "id": "doc-1",
        "project_id": "project-1",
        "status": "processing",
        "preprocessing_status": "processing",
        "preprocessing_metrics": {"source_chunk_count": 10},
        "chunk_count": 10,
        "structured_entries": 0,
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


async def _build_report(service: KnowledgeService, *, repo: Mock):
    return await service.processing_report(
        "project-1",
        "doc-1",
        "Bearer token",
        knowledge_repo_factory=Mock(return_value=repo),
        logger=Mock(),
    )


@pytest.mark.asyncio
async def test_processing_report_uses_answer_resolution_pending_state(
    service: KnowledgeService,
) -> None:
    repo = Mock()
    repo.get_document = AsyncMock(return_value=_document())
    repo.list_document_compiler_batches = AsyncMock(
        return_value=[
            SimpleNamespace(
                status="completed",
                batch_count=1,
                tokens_input=0,
                tokens_output=0,
                tokens_total=0,
            )
        ]
    )
    repo.get_document_answer_candidate_summary = AsyncMock(
        return_value=SimpleNamespace(
            raw_count=3, total_count=3, grounded_count=0, rejected_count=0
        )
    )
    repo.count_document_runtime_entries = AsyncMock(return_value=0)
    repo.count_document_retrieval_surface_entries = AsyncMock(return_value=0)
    repo.count_document_missing_embedding_entries = AsyncMock(return_value=0)
    repo.list_active_document_pipeline_jobs = AsyncMock(return_value=())

    report = await _build_report(service, repo=repo)
    assert report.state == "answer_resolution_pending"


@pytest.mark.asyncio
async def test_processing_report_returns_resume_action_when_raw_candidates_ready(
    service: KnowledgeService,
) -> None:
    repo = Mock()
    repo.get_document = AsyncMock(return_value=_document())
    repo.list_document_compiler_batches = AsyncMock(
        return_value=[
            SimpleNamespace(
                status="completed",
                batch_count=1,
                tokens_input=0,
                tokens_output=0,
                tokens_total=0,
            )
        ]
    )
    repo.get_document_answer_candidate_summary = AsyncMock(
        return_value=SimpleNamespace(
            raw_count=2, total_count=2, grounded_count=0, rejected_count=0
        )
    )
    repo.count_document_runtime_entries = AsyncMock(return_value=0)
    repo.count_document_retrieval_surface_entries = AsyncMock(return_value=0)
    repo.count_document_missing_embedding_entries = AsyncMock(return_value=0)
    repo.list_active_document_pipeline_jobs = AsyncMock(return_value=())

    report = await _build_report(service, repo=repo)
    action_ids = {item.id for item in report.allowed_actions}
    assert "resume_knowledge_compilation" in action_ids


@pytest.mark.asyncio
async def test_processing_report_returns_retry_action_when_failed_batches_exist(
    service: KnowledgeService,
) -> None:
    repo = Mock()
    repo.get_document = AsyncMock(return_value=_document())
    repo.list_document_compiler_batches = AsyncMock(
        return_value=[
            SimpleNamespace(
                status="failed",
                batch_count=1,
                tokens_input=0,
                tokens_output=0,
                tokens_total=0,
            )
        ]
    )
    repo.get_document_answer_candidate_summary = AsyncMock(
        return_value=SimpleNamespace(
            raw_count=1, total_count=1, grounded_count=0, rejected_count=0
        )
    )
    repo.count_document_runtime_entries = AsyncMock(return_value=0)
    repo.count_document_retrieval_surface_entries = AsyncMock(return_value=0)
    repo.count_document_missing_embedding_entries = AsyncMock(return_value=0)
    repo.list_active_document_pipeline_jobs = AsyncMock(return_value=())

    report = await _build_report(service, repo=repo)
    action_ids = {item.id for item in report.allowed_actions}
    assert "retry_failed_compiler_batches" in action_ids


@pytest.mark.asyncio
async def test_processing_report_returns_open_curation_console_when_canonical_entries_exist(
    service: KnowledgeService,
) -> None:
    repo = Mock()
    repo.get_document = AsyncMock(
        return_value=_document(preprocessing_metrics={"canonical_entry_count": 2})
    )
    repo.list_document_compiler_batches = AsyncMock(
        return_value=[
            SimpleNamespace(
                status="completed",
                batch_count=1,
                tokens_input=0,
                tokens_output=0,
                tokens_total=0,
            )
        ]
    )
    repo.get_document_answer_candidate_summary = AsyncMock(
        return_value=SimpleNamespace(
            raw_count=0, total_count=2, grounded_count=2, rejected_count=0
        )
    )
    repo.count_document_runtime_entries = AsyncMock(return_value=2)
    repo.count_document_retrieval_surface_entries = AsyncMock(return_value=2)
    repo.count_document_missing_embedding_entries = AsyncMock(return_value=0)
    repo.list_active_document_pipeline_jobs = AsyncMock(return_value=())

    report = await _build_report(service, repo=repo)
    action_ids = {item.id for item in report.allowed_actions}
    assert "open_curation_console" in action_ids


@pytest.mark.asyncio
async def test_processing_report_does_not_return_review_published_as_dead_span_action(
    service: KnowledgeService,
) -> None:
    repo = Mock()
    repo.get_document = AsyncMock(
        return_value=_document(preprocessing_metrics={"canonical_entry_count": 2})
    )
    repo.list_document_compiler_batches = AsyncMock(
        return_value=[
            SimpleNamespace(
                status="completed",
                batch_count=1,
                tokens_input=0,
                tokens_output=0,
                tokens_total=0,
            )
        ]
    )
    repo.get_document_answer_candidate_summary = AsyncMock(
        return_value=SimpleNamespace(
            raw_count=0, total_count=2, grounded_count=2, rejected_count=0
        )
    )
    repo.count_document_runtime_entries = AsyncMock(return_value=2)
    repo.count_document_retrieval_surface_entries = AsyncMock(return_value=2)
    repo.count_document_missing_embedding_entries = AsyncMock(return_value=0)
    repo.list_active_document_pipeline_jobs = AsyncMock(return_value=())

    report = await _build_report(service, repo=repo)
    action_ids = {item.id for item in report.actions}
    assert "review_published" not in action_ids
