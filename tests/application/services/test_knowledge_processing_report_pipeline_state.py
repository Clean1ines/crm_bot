from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.application.services.knowledge_service import KnowledgeService
from src.domain.project_plane.knowledge_pipeline import (
    KnowledgePipelineSnapshot,
    KnowledgePipelineState,
    allowed_actions_for_state,
)


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


def _repo_for_answer_resolution_pending() -> Mock:
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
    repo.count_document_canonical_entries = AsyncMock(return_value=0)
    repo.list_active_document_pipeline_jobs = AsyncMock(return_value=())
    return repo


async def _build_report(service: KnowledgeService, *, repo: Mock):
    return await service.processing_report(
        "project-1",
        "doc-1",
        "Bearer token",
        knowledge_repo_factory=Mock(return_value=repo),
        logger=Mock(),
    )


@pytest.mark.asyncio
async def test_processing_report_resume_enabled_when_not_running(
    service: KnowledgeService,
) -> None:
    report = await _build_report(service, repo=_repo_for_answer_resolution_pending())

    assert report.state == "answer_resolution_pending"
    resume_action = next(
        action
        for action in report.allowed_actions
        if action.id == "resume_knowledge_compilation"
    )
    assert resume_action.enabled is True
    assert resume_action.blocker_code == ""
    assert resume_action.reason == ""

    action_ids = {item.id for item in report.allowed_actions}
    assert "publish_raw_drafts_without_resolution" in action_ids


@pytest.mark.asyncio
async def test_processing_report_does_not_silently_drop_domain_actions(
    service: KnowledgeService,
) -> None:
    report = await _build_report(service, repo=_repo_for_answer_resolution_pending())

    snapshot = KnowledgePipelineSnapshot(
        document_id="doc-1",
        document_status="processing",
        preprocessing_status="processing",
        preprocessing_stage=None,
        source_unit_count=10,
        compiler_batch_total_count=1,
        compiler_batch_completed_count=1,
        compiler_batch_failed_count=0,
        compiler_batch_processing_count=0,
        compiler_batch_pending_count=0,
        raw_candidate_count=2,
        canonical_entry_count=0,
        runtime_entry_count=0,
        retrieval_surface_count=0,
        missing_embedding_count=0,
        active_job_count=0,
        active_job_type=None,
        active_job_status=None,
        active_error_code=None,
        active_error_retryable=False,
        last_error_code=None,
        metrics={"source_chunk_count": 10},
    )
    domain_actions = allowed_actions_for_state(
        KnowledgePipelineState.ANSWER_RESOLUTION_PENDING,
        snapshot,
    )
    assert any(
        action.value == "resume_knowledge_compilation" for action in domain_actions
    )
    assert any(
        action.id == "resume_knowledge_compilation" for action in report.allowed_actions
    )


@pytest.mark.asyncio
async def test_recommended_next_action_prefers_enabled_resume(
    service: KnowledgeService,
) -> None:
    report = await _build_report(service, repo=_repo_for_answer_resolution_pending())

    assert report.recommended_next_action is not None
    assert report.recommended_next_action["id"] == "resume_knowledge_compilation"
    assert report.recommended_next_action["enabled"] is True


@pytest.mark.asyncio
async def test_fallback_publish_action_is_secondary_warning_with_reason(
    service: KnowledgeService,
) -> None:
    report = await _build_report(service, repo=_repo_for_answer_resolution_pending())

    publish_action = next(
        action
        for action in report.allowed_actions
        if action.id == "publish_raw_drafts_without_resolution"
    )
    assert publish_action.kind == "secondary_warning"
    assert publish_action.reason


@pytest.mark.asyncio
async def test_processing_report_resume_disabled_when_pipeline_running(
    service: KnowledgeService,
) -> None:
    repo = _repo_for_answer_resolution_pending()
    repo.get_document = AsyncMock(
        return_value=_document(status="processing", preprocessing_status="processing")
    )
    report = await _build_report(service, repo=repo)
    resume_action = next(
        action
        for action in report.allowed_actions
        if action.id == "resume_knowledge_compilation"
    )
    assert resume_action.enabled is False
    assert resume_action.blocker_code == "pipeline_already_running"


@pytest.mark.asyncio
async def test_resume_document_processing_enqueues_resume_task(
    service: KnowledgeService,
) -> None:
    repo = _repo_for_answer_resolution_pending()
    queue_repo = Mock()
    queue_repo.enqueue = AsyncMock(return_value="job-1")

    result = await service.resume_document_processing(
        "project-1",
        "doc-1",
        "Bearer token",
        queue_repo=queue_repo,
        resume_processing_task_type="resume_knowledge_processing",
        logger=Mock(),
        knowledge_repo_factory=Mock(return_value=repo),
    )

    assert result["status"] == "queued"
    payload = queue_repo.enqueue.await_args.kwargs["payload"]
    assert payload["project_id"] == "project-1"
    assert payload["document_id"] == "doc-1"
    assert payload["requested_by"] == "user-1"
    assert payload["source"] == "knowledge_resume_processing"


@pytest.mark.asyncio
async def test_resume_document_processing_rejects_state_without_resume_action(
    service: KnowledgeService,
) -> None:
    repo = _repo_for_answer_resolution_pending()
    repo.get_document = AsyncMock(
        return_value=_document(
            status="processed", preprocessing_status="completed", structured_entries=1
        )
    )
    queue_repo = Mock()
    queue_repo.enqueue = AsyncMock(return_value="job-1")

    with pytest.raises(Exception):
        await service.resume_document_processing(
            "project-1",
            "doc-1",
            "Bearer token",
            queue_repo=queue_repo,
            resume_processing_task_type="resume_knowledge_processing",
            logger=Mock(),
            knowledge_repo_factory=Mock(return_value=repo),
        )
