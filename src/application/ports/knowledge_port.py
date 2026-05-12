from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from src.domain.control_plane.project_views import ProjectSummaryView
from src.domain.project_plane.json_types import JsonObject
from src.domain.project_plane.knowledge_compilation import (
    AnswerCandidate,
    CandidateCluster,
    CanonicalKnowledgeEntry,
    CompilationMetrics,
    CompilerRun,
    SourceChunk,
)
from src.domain.project_plane.knowledge_preprocessing import (
    KnowledgePreprocessingEntry,
    KnowledgePreprocessingExecutionResult,
    KnowledgePreprocessingMode,
)
from src.domain.project_plane.knowledge_views import KnowledgeSearchResultView
from src.domain.project_plane.model_usage_views import (
    ModelUsageEventCreate,
    ModelUsageSummaryView,
)


class KnowledgeDbPoolPort(Protocol):
    """Opaque DB pool passed through to infrastructure repository factories."""


class KnowledgeProjectAccessPort(Protocol):
    async def user_has_project_role(
        self,
        project_id: str,
        user_id: str,
        allowed_roles: Sequence[str],
    ) -> bool: ...

    async def get_project_view(self, project_id: str) -> ProjectSummaryView | None: ...

    async def project_exists(self, project_id: str) -> bool: ...


class PlatformUserAdminPort(Protocol):
    async def is_platform_admin(self, user_id: str) -> bool: ...


class JwtDecoderPort(Protocol):
    ExpiredSignatureError: type[Exception]
    InvalidTokenError: type[Exception]

    def decode(
        self,
        token: str,
        secret: str,
        algorithms: list[str],
    ) -> JsonObject: ...


class KnowledgeRepositoryPort(Protocol):
    async def create_document(
        self,
        project_id: str,
        file_name: str,
        file_size: int | None = None,
        uploaded_by: str | None = None,
    ) -> str: ...

    async def add_source_chunks(
        self,
        *,
        project_id: str,
        document_id: str,
        chunks: Sequence[SourceChunk],
    ) -> int: ...

    async def add_canonical_entries(
        self,
        *,
        project_id: str,
        document_id: str,
        entries: Sequence[CanonicalKnowledgeEntry],
    ) -> int: ...

    async def create_compiler_run(self, run: CompilerRun) -> None: ...

    async def complete_compiler_run(
        self,
        compiler_run_id: str,
        metrics: CompilationMetrics,
    ) -> None: ...

    async def fail_compiler_run(
        self,
        compiler_run_id: str,
        error: str,
    ) -> None: ...

    async def add_answer_candidates(
        self,
        *,
        project_id: str,
        document_id: str,
        candidates: Sequence[AnswerCandidate],
    ) -> int: ...

    async def add_candidate_clusters(
        self,
        *,
        project_id: str,
        document_id: str,
        clusters: Sequence[CandidateCluster],
    ) -> int: ...

    async def delete_document_chunks(self, document_id: str) -> None: ...

    async def update_document_status(
        self,
        document_id: str,
        status: str,
        error: str | None = None,
    ) -> None: ...

    async def update_document_preprocessing_status(
        self,
        document_id: str,
        *,
        mode: KnowledgePreprocessingMode,
        status: str,
        error: str | None = None,
        model: str | None = None,
        prompt_version: str | None = None,
        metrics: JsonObject | None = None,
    ) -> None: ...

    async def search(
        self,
        project_id: str,
        query: str,
        limit: int = 10,
        hybrid_fallback: bool = True,
        thread_id: str | None = None,
    ) -> list[KnowledgeSearchResultView]: ...

    async def preview_search(
        self,
        project_id: str,
        query: str,
        limit: int = 10,
    ) -> list[KnowledgeSearchResultView]: ...

    async def clear_project_knowledge(self, project_id: str) -> None: ...


class KnowledgeRepositoryFactoryPort(Protocol):
    def __call__(self, pool: KnowledgeDbPoolPort) -> KnowledgeRepositoryPort: ...


class KnowledgeQueuePort(Protocol):
    async def enqueue(
        self,
        task_type: str,
        payload: JsonObject | None = None,
        max_attempts: int = 3,
    ) -> str: ...


class KnowledgeChunkerPort(Protocol):
    async def process_file(
        self, file_content: bytes | bytearray, file_name: str
    ) -> list[str | JsonObject]: ...


class KnowledgeChunkerFactoryPort(Protocol):
    def __call__(self) -> KnowledgeChunkerPort: ...


class KnowledgePreprocessorPort(Protocol):
    async def preprocess(
        self,
        *,
        mode: KnowledgePreprocessingMode,
        chunks: list[JsonObject],
        file_name: str,
        previous_entry_titles: Sequence[str] = (),
    ) -> KnowledgePreprocessingExecutionResult: ...

    async def merge_answer_entry(
        self,
        *,
        mode: KnowledgePreprocessingMode,
        file_name: str,
        existing_entry: KnowledgePreprocessingEntry,
        incoming_entry: KnowledgePreprocessingEntry,
    ) -> KnowledgePreprocessingExecutionResult: ...


class KnowledgePreprocessorFactoryPort(Protocol):
    def __call__(self) -> KnowledgePreprocessorPort: ...


class ModelUsageRepositoryPort(Protocol):
    async def record_event(self, event: ModelUsageEventCreate) -> None: ...

    async def get_project_usage_summary(
        self,
        *,
        project_id: str,
        month_start_utc: object,
        month_end_utc: object,
        today_start_utc: object,
        monthly_budget_tokens: int,
    ) -> ModelUsageSummaryView: ...


class ModelUsageRepositoryFactoryPort(Protocol):
    def __call__(self, pool: KnowledgeDbPoolPort) -> ModelUsageRepositoryPort: ...
