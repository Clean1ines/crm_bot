from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from src.application.errors import ValidationError
from src.application.services.knowledge_service import KnowledgeService
from src.domain.control_plane.project_views import ProjectSummaryView
from src.domain.project_plane.json_types import JsonObject
from src.domain.project_plane.knowledge_document_lifecycle import (
    LEGACY_USER_CANCELLED_MESSAGE,
    NON_RETRYABLE_INPUT_TOO_LARGE_STATUS,
    PROCESSING_PAUSED_QUOTA_STATUS,
)
from src.domain.project_plane.knowledge_preprocessing import MODE_FAQ
from src.infrastructure.llm.knowledge_surface_graph_compiler_v2 import (
    GRAPH_PROMPT_VERSION,
)
from src.domain.project_plane.retrieval_surface_compilation import (
    RetrievalSurfaceCompilerRun,
    RetrievalSurfaceSourceUnit,
    SurfaceCompilerRunStatus,
)


@dataclass(slots=True)
class Document:
    id: str = "document-1"
    project_id: str = "project-1"
    file_name: str = "faq.md"
    status: str = "error"
    preprocessing_status: str | None = "failed"
    preprocessing_error: str | None = LEGACY_USER_CANCELLED_MESSAGE
    preprocessing_metrics: dict[str, object] | None = None
    preprocessing_model: str | None = "fake-model"
    preprocessing_prompt_version: str | None = GRAPH_PROMPT_VERSION
    chunk_count: int = 1
    structured_entries: int = 0
    created_at: datetime = datetime.now(timezone.utc)
    updated_at: datetime = datetime.now(timezone.utc)


class Jwt:
    ExpiredSignatureError: type[Exception] = Exception
    InvalidTokenError: type[Exception] = Exception

    def decode(
        self,
        token: str,
        secret: str,
        algorithms: list[str],
    ) -> JsonObject:
        del token, secret, algorithms
        return {"sub": "user-1"}


class ProjectRepo:
    async def project_exists(self, project_id: str) -> bool:
        return project_id == "project-1"

    async def user_has_project_role(
        self,
        project_id: str,
        user_id: str,
        allowed_roles: Sequence[str],
    ) -> bool:
        del project_id, user_id, allowed_roles
        return True

    async def get_project_view(self, project_id: str) -> ProjectSummaryView | None:
        del project_id
        return None


class UserRepo:
    async def is_platform_admin(self, user_id: str) -> bool:
        del user_id
        return False


class QueueRepo:
    def __init__(self) -> None:
        self.payload: JsonObject | None = None

    async def enqueue(
        self,
        task_type: str,
        payload: JsonObject | None = None,
        max_attempts: int = 3,
    ) -> str:
        del task_type, max_attempts
        self.payload = payload
        return "job-1"


class Logger:
    def debug(self, *_args: object, **_kwargs: object) -> None:
        return None

    def info(self, *_args: object, **_kwargs: object) -> None:
        return None

    def warning(self, *_args: object, **_kwargs: object) -> None:
        return None

    def error(self, *_args: object, **_kwargs: object) -> None:
        return None

    def exception(self, *_args: object, **_kwargs: object) -> None:
        return None


class Repo:
    def __init__(
        self,
        *,
        document: Document,
        run: RetrievalSurfaceCompilerRun | None,
        source_units: tuple[RetrievalSurfaceSourceUnit, ...],
    ) -> None:
        self.document = document
        self.run = run
        self.source_units = source_units
        self.resume_metrics: dict[str, object] | None = None

    async def get_document(self, document_id: str) -> Document | None:
        del document_id
        return self.document

    async def get_latest_surface_run_for_document(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> RetrievalSurfaceCompilerRun | None:
        del project_id, document_id
        return self.run

    async def list_surface_source_units_for_run(
        self,
        *,
        run_id: str,
    ) -> tuple[RetrievalSurfaceSourceUnit, ...]:
        del run_id
        return self.source_units

    async def resume_document_processing(
        self,
        *,
        project_id: str,
        document_id: str,
        mode: str,
        model: str | None,
        prompt_version: str | None,
        metrics: dict[str, object],
    ) -> bool:
        del project_id, document_id, mode, model, prompt_version
        self.resume_metrics = metrics
        return True


def _service() -> KnowledgeService:
    return KnowledgeService(
        project_repo=ProjectRepo(),
        user_repo=UserRepo(),
        pool=object(),
        jwt_secret="test-secret",
        jwt_module=Jwt(),
    )


def _run(
    *,
    status: SurfaceCompilerRunStatus = "cancelled",
    error_type: str | None = "processing_cancelled",
) -> RetrievalSurfaceCompilerRun:
    return RetrievalSurfaceCompilerRun(
        id="run-1",
        project_id="project-1",
        document_id="document-1",
        mode=MODE_FAQ,
        status=status,
        compiler_kind="faq_retrieval_surface_compiler",
        model="fake-model",
        prompt_version=GRAPH_PROMPT_VERSION,
        error_type=error_type,
    )


def _source_unit() -> RetrievalSurfaceSourceUnit:
    return RetrievalSurfaceSourceUnit(
        id="unit-1",
        run_id="run-1",
        document_id="document-1",
        source_unit_key="unit-1",
        source_chunk_indexes=(0,),
        title="FAQ",
        body="Answer",
        children=(),
        raw_text="Answer",
        section_path=(),
        source_refs=("chunk:0",),
        preprocessing_mode=MODE_FAQ,
        metadata={},
    )


def _repo_factory(repo: Repo):
    def make_repo(_pool: object) -> Repo:
        return repo

    return make_repo


@pytest.mark.asyncio
async def test_resume_document_processing_requires_manual_lifecycle_permission() -> (
    None
):
    repo = Repo(
        document=Document(
            status=PROCESSING_PAUSED_QUOTA_STATUS,
            preprocessing_status=PROCESSING_PAUSED_QUOTA_STATUS,
            preprocessing_error=None,
        ),
        run=_run(status="failed", error_type="GroqFallbackExhaustedError"),
        source_units=(_source_unit(),),
    )

    with pytest.raises(ValidationError, match="does not allow manual FAQ resume"):
        await _service().resume_document_processing(
            project_id="project-1",
            document_id="document-1",
            authorization="Bearer token",
            knowledge_repo_factory=_repo_factory(repo),
            queue_repo=QueueRepo(),
            knowledge_upload_task_type="process_knowledge_upload",
            expected_faq_surface_prompt_version=GRAPH_PROMPT_VERSION,
            logger=Logger(),
        )

    assert repo.resume_metrics is None


@pytest.mark.asyncio
async def test_resume_document_processing_authorizes_user_cancelled_run_for_worker() -> (
    None
):
    repo = Repo(
        document=Document(),
        run=_run(status="cancelled", error_type="processing_cancelled"),
        source_units=(_source_unit(),),
    )
    queue = QueueRepo()

    result = await _service().resume_document_processing(
        project_id="project-1",
        document_id="document-1",
        authorization="Bearer token",
        knowledge_repo_factory=_repo_factory(repo),
        queue_repo=queue,
        knowledge_upload_task_type="process_knowledge_upload",
        expected_faq_surface_prompt_version=GRAPH_PROMPT_VERSION,
        logger=Logger(),
    )

    assert result["status"] == "queued"
    assert queue.payload is not None
    assert queue.payload["resume_run_id"] == "run-1"
    assert queue.payload["source"] == "knowledge_document_resume"
    assert repo.resume_metrics is not None
    assert repo.resume_metrics["manual_resume_authorized_by_lifecycle"] is True
    assert repo.resume_metrics["authorized_resume_run_id"] == "run-1"
    assert repo.resume_metrics["resume_policy_before_resume"] == "manual_only"


@pytest.mark.asyncio
async def test_resume_document_processing_rejects_input_too_large_document() -> None:
    repo = Repo(
        document=Document(
            status="error",
            preprocessing_status=NON_RETRYABLE_INPUT_TOO_LARGE_STATUS,
            preprocessing_error="input too large",
        ),
        run=_run(status="failed", error_type="input_too_large"),
        source_units=(_source_unit(),),
    )
    queue = QueueRepo()

    with pytest.raises(ValidationError, match="does not allow manual FAQ resume"):
        await _service().resume_document_processing(
            project_id="project-1",
            document_id="document-1",
            authorization="Bearer token",
            knowledge_repo_factory=_repo_factory(repo),
            queue_repo=queue,
            knowledge_upload_task_type="process_knowledge_upload",
            expected_faq_surface_prompt_version=GRAPH_PROMPT_VERSION,
            logger=Logger(),
        )

    assert queue.payload is None
    assert repo.resume_metrics is None


@pytest.mark.asyncio
async def test_resume_document_processing_rejects_fatal_failed_document() -> None:
    repo = Repo(
        document=Document(
            status="error",
            preprocessing_status="failed",
            preprocessing_error="fatal backend error",
        ),
        run=_run(status="failed", error_type="RuntimeError"),
        source_units=(_source_unit(),),
    )
    queue = QueueRepo()

    with pytest.raises(ValidationError, match="does not allow manual FAQ resume"):
        await _service().resume_document_processing(
            project_id="project-1",
            document_id="document-1",
            authorization="Bearer token",
            knowledge_repo_factory=_repo_factory(repo),
            queue_repo=queue,
            knowledge_upload_task_type="process_knowledge_upload",
            expected_faq_surface_prompt_version=GRAPH_PROMPT_VERSION,
            logger=Logger(),
        )

    assert queue.payload is None
    assert repo.resume_metrics is None


@pytest.mark.asyncio
async def test_resume_document_processing_rejects_manual_cancel_without_saved_source_units() -> (
    None
):
    repo = Repo(
        document=Document(),
        run=_run(status="cancelled", error_type="processing_cancelled"),
        source_units=(),
    )
    queue = QueueRepo()

    with pytest.raises(ValidationError, match="No saved FAQ source units found"):
        await _service().resume_document_processing(
            project_id="project-1",
            document_id="document-1",
            authorization="Bearer token",
            knowledge_repo_factory=_repo_factory(repo),
            queue_repo=queue,
            knowledge_upload_task_type="process_knowledge_upload",
            expected_faq_surface_prompt_version=GRAPH_PROMPT_VERSION,
            logger=Logger(),
        )

    assert queue.payload is None
    assert repo.resume_metrics is None


@pytest.mark.asyncio
async def test_resume_document_processing_rejects_stale_prompt_version_run() -> None:
    repo = Repo(
        document=Document(),
        run=RetrievalSurfaceCompilerRun(
            id="run-1",
            project_id="project-1",
            document_id="document-1",
            mode=MODE_FAQ,
            status="cancelled",
            compiler_kind="faq_retrieval_surface_compiler",
            model="fake-model",
            prompt_version="stale-faq-surface-prompt-version",
            error_type="processing_cancelled",
        ),
        source_units=(_source_unit(),),
    )
    queue = QueueRepo()

    with pytest.raises(ValidationError, match="does not allow manual FAQ resume"):
        await _service().resume_document_processing(
            project_id="project-1",
            document_id="document-1",
            authorization="Bearer token",
            knowledge_repo_factory=_repo_factory(repo),
            queue_repo=queue,
            knowledge_upload_task_type="process_knowledge_upload",
            expected_faq_surface_prompt_version=GRAPH_PROMPT_VERSION,
            logger=Logger(),
        )

    assert queue.payload is None
    assert repo.resume_metrics is None
