from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import pytest

from src.application.errors import ValidationError
from src.application.services.knowledge_surface_ingestion_service import (
    KnowledgeFaqSurfaceIngestionService,
    _should_reuse_surface_run,
)
from src.infrastructure.llm.knowledge_surface_graph_compiler_v2 import (
    GRAPH_PROMPT_VERSION,
)
from src.domain.project_plane.knowledge_artifact_cleanup import (
    KnowledgeArtifactCleanupPlan,
    KnowledgeArtifactCleanupResult,
)
from src.domain.project_plane.knowledge_document_lifecycle import (
    LEGACY_USER_CANCELLED_MESSAGE,
    PROCESSING_PAUSED_QUOTA_STATUS,
    TRIGGER_EXPLICIT_USER_RESUME,
    TRIGGER_NORMAL_UPLOAD,
    TRIGGER_QUOTA_RECOVERY,
    resolve_knowledge_document_lifecycle,
)
from src.domain.project_plane.knowledge_preprocessing import MODE_FAQ
from src.domain.project_plane.retrieval_surface_compilation import (
    RetrievalSurfaceCompilerRun,
    RetrievalSurfaceSourceUnit,
)


PROMPT_VERSION = GRAPH_PROMPT_VERSION


@dataclass(slots=True)
class Document:
    project_id: str = "project-1"
    id: str = "document-1"
    file_name: str = "faq.md"
    status: str = "uploaded"
    preprocessing_status: str | None = None
    preprocessing_error: str | None = None
    preprocessing_metrics: dict[str, object] | None = None
    preprocessing_model: str | None = "fake-model"
    preprocessing_prompt_version: str | None = PROMPT_VERSION
    chunk_count: int = 1
    structured_entries: int = 0


class Logger:
    def info(self, *_args: object, **_kwargs: object) -> None:
        return None

    def warning(self, *_args: object, **_kwargs: object) -> None:
        return None


@dataclass(slots=True)
class Graph:
    source_units: tuple[RetrievalSurfaceSourceUnit, ...]
    surfaces: tuple[object, ...] = ()
    relations: tuple[object, ...] = ()
    ownership: tuple[object, ...] = ()
    reassignments: tuple[object, ...] = ()
    merge_decisions: tuple[object, ...] = ()


@dataclass(slots=True)
class CompileResult:
    graph: Graph
    model: str
    prompt_version: str
    metrics: dict[str, object]


class Compiler:
    model_name = "fake-model"

    async def compile_surfaces(
        self,
        *,
        mode: str,
        source_units: tuple[RetrievalSurfaceSourceUnit, ...],
        file_name: str,
        run_id: str,
    ) -> CompileResult:
        del mode, file_name, run_id
        return CompileResult(
            graph=Graph(source_units=tuple(source_units)),
            model=self.model_name,
            prompt_version=PROMPT_VERSION,
            metrics={},
        )


class Repo:
    def __init__(
        self,
        *,
        document: Document,
        latest_run: RetrievalSurfaceCompilerRun | None = None,
        existing_source_units: tuple[RetrievalSurfaceSourceUnit, ...] = (),
    ) -> None:
        self.document = document
        self.latest_run = latest_run
        self.existing_source_units = existing_source_units
        self.cleanup_calls = 0
        self.created_runs: list[RetrievalSurfaceCompilerRun] = []
        self.updated_runs: list[tuple[str, str]] = []
        self.statuses: list[tuple[str, str, str | None]] = []
        self.saved_source_units: tuple[RetrievalSurfaceSourceUnit, ...] = ()

    async def get_document(self, document_id: str) -> Document | None:
        del document_id
        return self.document

    async def cleanup_document_artifacts(
        self,
        plan: KnowledgeArtifactCleanupPlan,
    ) -> KnowledgeArtifactCleanupResult:
        self.cleanup_calls += 1
        return KnowledgeArtifactCleanupResult(plan=plan)

    async def delete_document_chunks(self, document_id: str) -> None:
        del document_id

    async def is_document_processing_cancelled(self, document_id: str) -> bool:
        del document_id
        return False

    async def get_latest_surface_run_for_document(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> RetrievalSurfaceCompilerRun | None:
        del project_id, document_id
        return self.latest_run

    async def list_surface_source_units_for_run(
        self,
        *,
        run_id: str,
    ) -> tuple[RetrievalSurfaceSourceUnit, ...]:
        del run_id
        return self.existing_source_units

    async def list_surfaces_for_run(self, *, run_id: str) -> tuple[object, ...]:
        del run_id
        return ()

    async def add_source_chunks(self, **_kwargs: object) -> int:
        return 1

    async def create_surface_compiler_run(
        self,
        run: RetrievalSurfaceCompilerRun,
    ) -> RetrievalSurfaceCompilerRun:
        self.created_runs.append(run)
        return run

    async def update_surface_compiler_run_status(
        self,
        *,
        run_id: str,
        status: str,
        error_type: str | None = None,
        error_message: str | None = None,
    ) -> None:
        del error_type, error_message
        self.updated_runs.append((run_id, status))

    async def create_surface_compiler_stage(self, stage: object) -> object:
        return stage

    async def list_surface_stages_for_run(self, *, run_id: str) -> tuple[object, ...]:
        del run_id
        return ()

    async def save_surface_source_units(
        self,
        *,
        run_id: str,
        document_id: str,
        source_units: tuple[RetrievalSurfaceSourceUnit, ...],
    ) -> None:
        del run_id, document_id
        self.saved_source_units = source_units

    async def save_surfaces(self, **_kwargs: object) -> None:
        return None

    async def save_surface_relations(self, **_kwargs: object) -> None:
        return None

    async def save_surface_question_ownership(self, **_kwargs: object) -> None:
        return None

    async def save_surface_question_reassignments(self, **_kwargs: object) -> None:
        return None

    async def save_surface_merge_decisions(self, **_kwargs: object) -> None:
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
        del document_id, mode, model, prompt_version, metrics
        self.statuses.append(("preprocessing", status, error))

    async def update_document_status(
        self,
        document_id: str,
        status: str,
        error: str | None = None,
    ) -> None:
        del document_id
        self.statuses.append(("document", status, error))


def _run(
    *,
    run_id: str = "run-1",
    status: str = "cancelled",
    error_type: str | None = "processing_cancelled",
) -> RetrievalSurfaceCompilerRun:
    return RetrievalSurfaceCompilerRun(
        id=run_id,
        project_id="project-1",
        document_id="document-1",
        mode=MODE_FAQ,
        status=status,
        compiler_kind="faq_retrieval_surface_compiler",
        model="fake-model",
        prompt_version=PROMPT_VERSION,
        started_at=datetime.now(timezone.utc),
        error_type=error_type,
    )


def _source_unit(run_id: str = "run-1") -> RetrievalSurfaceSourceUnit:
    return RetrievalSurfaceSourceUnit(
        id="unit-1",
        run_id=run_id,
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


def _factory(repo: Repo):
    def make_repo(_pool: object) -> Repo:
        return repo

    return make_repo


def _compiler_factory() -> Compiler:
    return Compiler()


def test_explicit_resume_policy_uses_authorized_lifecycle_marker_after_status_mutation() -> (
    None
):
    document = Document(
        status="processing",
        preprocessing_status="processing",
        preprocessing_metrics={
            "manual_resume_authorized_by_lifecycle": True,
            "authorized_resume_run_id": "run-1",
        },
    )
    decision = resolve_knowledge_document_lifecycle(
        document_status=document.status,
        preprocessing_status=document.preprocessing_status,
        preprocessing_error=document.preprocessing_error,
        preprocessing_metrics=document.preprocessing_metrics,
        chunk_count=document.chunk_count,
    )

    assert _should_reuse_surface_run(
        latest_run=_run(run_id="run-1"),
        lifecycle_trigger=TRIGGER_EXPLICIT_USER_RESUME,
        resume_run_id="run-1",
        lifecycle_decision=decision,
        existing_document=document,
    )


def test_quota_recovery_policy_does_not_reuse_user_cancelled_run() -> None:
    document = Document(
        status=PROCESSING_PAUSED_QUOTA_STATUS,
        preprocessing_status=PROCESSING_PAUSED_QUOTA_STATUS,
    )
    decision = resolve_knowledge_document_lifecycle(
        document_status=document.status,
        preprocessing_status=document.preprocessing_status,
        preprocessing_error=None,
        preprocessing_metrics=None,
    )

    assert not _should_reuse_surface_run(
        latest_run=_run(run_id="run-1", status="cancelled"),
        lifecycle_trigger=TRIGGER_QUOTA_RECOVERY,
        resume_run_id="run-1",
        lifecycle_decision=decision,
        existing_document=document,
    )


@pytest.mark.asyncio
async def test_invalid_new_upload_does_not_cleanup_existing_artifacts() -> None:
    repo = Repo(document=Document(), latest_run=_run())
    service = KnowledgeFaqSurfaceIngestionService(pool=object())

    with pytest.raises(ValidationError, match="No indexable FAQ source units"):
        await service.process_document(
            project_id="project-1",
            document_id="document-1",
            file_name="faq.md",
            chunks=[{"content": "---"}],
            knowledge_repo_factory=_factory(repo),
            surface_compiler_factory=_compiler_factory,
            logger=Logger(),
            lifecycle_trigger=TRIGGER_NORMAL_UPLOAD,
        )

    assert repo.cleanup_calls == 0
    assert repo.created_runs == []


@pytest.mark.asyncio
async def test_normal_upload_after_user_cancel_creates_new_run_and_cleans_up() -> None:
    repo = Repo(
        document=Document(
            status="error",
            preprocessing_status="failed",
            preprocessing_error=LEGACY_USER_CANCELLED_MESSAGE,
        ),
        latest_run=_run(run_id="old-run", status="cancelled"),
    )
    service = KnowledgeFaqSurfaceIngestionService(pool=object())

    await service.process_document(
        project_id="project-1",
        document_id="document-1",
        file_name="faq.md",
        chunks=[{"content": "Question? Answer."}],
        knowledge_repo_factory=_factory(repo),
        surface_compiler_factory=_compiler_factory,
        logger=Logger(),
        lifecycle_trigger=TRIGGER_NORMAL_UPLOAD,
    )

    assert repo.cleanup_calls == 1
    assert len(repo.created_runs) == 1
    assert repo.created_runs[0].id != "old-run"


@pytest.mark.asyncio
async def test_explicit_resume_reuses_matching_user_cancelled_run() -> None:
    repo = Repo(
        document=Document(
            status="processing",
            preprocessing_status="processing",
            preprocessing_metrics={
                "manual_resume_authorized_by_lifecycle": True,
                "authorized_resume_run_id": "run-1",
            },
        ),
        latest_run=_run(run_id="run-1", status="cancelled"),
        existing_source_units=(_source_unit("run-1"),),
    )
    service = KnowledgeFaqSurfaceIngestionService(pool=object())

    await service.process_document(
        project_id="project-1",
        document_id="document-1",
        file_name="faq.md",
        chunks=[{"content": "Question? Answer."}],
        knowledge_repo_factory=_factory(repo),
        surface_compiler_factory=_compiler_factory,
        logger=Logger(),
        lifecycle_trigger=TRIGGER_EXPLICIT_USER_RESUME,
        resume_run_id="run-1",
    )

    assert repo.cleanup_calls == 0
    assert repo.created_runs == []
    assert ("run-1", "running") in repo.updated_runs


@pytest.mark.asyncio
async def test_quota_recovery_reuses_failed_non_cancelled_run_when_lifecycle_allows_auto() -> (
    None
):
    repo = Repo(
        document=Document(
            status=PROCESSING_PAUSED_QUOTA_STATUS,
            preprocessing_status=PROCESSING_PAUSED_QUOTA_STATUS,
        ),
        latest_run=_run(
            run_id="run-1",
            status="failed",
            error_type="GroqFallbackExhaustedError",
        ),
        existing_source_units=(_source_unit("run-1"),),
    )
    service = KnowledgeFaqSurfaceIngestionService(pool=object())

    await service.process_document(
        project_id="project-1",
        document_id="document-1",
        file_name="faq.md",
        chunks=[{"content": "Question? Answer."}],
        knowledge_repo_factory=_factory(repo),
        surface_compiler_factory=_compiler_factory,
        logger=Logger(),
        lifecycle_trigger=TRIGGER_QUOTA_RECOVERY,
        resume_run_id="run-1",
    )

    assert repo.cleanup_calls == 0
    assert repo.created_runs == []
    assert ("run-1", "running") in repo.updated_runs


@pytest.mark.asyncio
async def test_quota_recovery_refuses_user_cancelled_run_without_destructive_cleanup() -> (
    None
):
    repo = Repo(
        document=Document(
            status=PROCESSING_PAUSED_QUOTA_STATUS,
            preprocessing_status=PROCESSING_PAUSED_QUOTA_STATUS,
        ),
        latest_run=_run(run_id="run-1", status="cancelled"),
    )
    service = KnowledgeFaqSurfaceIngestionService(pool=object())

    with pytest.raises(ValidationError, match="not allowed by document lifecycle"):
        await service.process_document(
            project_id="project-1",
            document_id="document-1",
            file_name="faq.md",
            chunks=[{"content": "Question? Answer."}],
            knowledge_repo_factory=_factory(repo),
            surface_compiler_factory=_compiler_factory,
            logger=Logger(),
            lifecycle_trigger=TRIGGER_QUOTA_RECOVERY,
            resume_run_id="run-1",
        )

    assert repo.cleanup_calls == 0
    assert repo.created_runs == []
