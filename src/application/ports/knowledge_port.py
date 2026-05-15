from __future__ import annotations

from dataclasses import dataclass

from collections.abc import Sequence
from typing import Protocol

from src.domain.control_plane.project_views import ProjectSummaryView
from src.domain.project_plane.json_types import JsonObject
from src.domain.project_plane.knowledge_compilation import (
    AnswerCandidate,
    CandidateCluster,
    CanonicalKnowledgeEntry,
    CompilerBatch,
    CompilationMetrics,
    CompilerRun,
    SourceChunk,
)
from src.domain.project_plane.knowledge_preprocessing import (
    KnowledgeAnswerMergeExecutionResult,
    KnowledgePreprocessingEntry,
    KnowledgePreprocessingExecutionResult,
    KnowledgePreprocessingMode,
    KnowledgeQuestionIntentCard,
    KnowledgeSemanticMergeExecutionResult,
    KnowledgeSemanticMergeGroup,
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


@dataclass(frozen=True, slots=True)
class KnowledgeDocumentRuntimeEntries:
    project_id: str
    document_id: str
    file_name: str
    preprocessing_mode: str
    entries: tuple[CanonicalKnowledgeEntry, ...]


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

    async def create_compiler_batches(
        self,
        *,
        project_id: str,
        document_id: str,
        batches: Sequence[CompilerBatch],
    ) -> int: ...

    async def mark_compiler_batch_processing(
        self,
        batch_id: str,
        *,
        attempt_count: int,
    ) -> None: ...

    async def complete_compiler_batch(
        self,
        batch_id: str,
        *,
        model: str,
        prompt_version: str,
        tokens_input: int,
        tokens_output: int,
        tokens_total: int,
    ) -> None: ...

    async def fail_compiler_batch(
        self,
        batch_id: str,
        *,
        error_type: str,
        error_message: str,
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

    async def cancel_document_processing(
        self,
        *,
        project_id: str,
        document_id: str,
        reason: str,
    ) -> bool: ...

    async def is_document_processing_cancelled(self, document_id: str) -> bool: ...

    async def list_runtime_entry_titles(
        self,
        *,
        project_id: str,
        exclude_document_id: str | None = None,
        limit: int = 300,
    ) -> tuple[str, ...]: ...

    async def list_document_runtime_entries(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> tuple[CanonicalKnowledgeEntry, ...]: ...

    async def apply_document_semantic_retightening(
        self,
        *,
        project_id: str,
        document_id: str,
        updated_entries: Sequence[CanonicalKnowledgeEntry],
        archived_entry_ids: Sequence[str],
        metrics: JsonObject,
    ) -> JsonObject: ...

    async def load_document_runtime_entries(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> KnowledgeDocumentRuntimeEntries | None: ...

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
    @property
    def model_name(self) -> str: ...

    async def preprocess(
        self,
        *,
        mode: KnowledgePreprocessingMode,
        chunks: list[JsonObject],
        file_name: str,
        previous_question_intents: Sequence[KnowledgeQuestionIntentCard] = (),
    ) -> KnowledgePreprocessingExecutionResult: ...

    async def merge_known_answer(
        self,
        *,
        mode: KnowledgePreprocessingMode,
        file_name: str,
        known_intent: KnowledgePreprocessingEntry,
        incoming_fragment: KnowledgePreprocessingEntry,
    ) -> KnowledgeAnswerMergeExecutionResult: ...

    async def tighten_semantic_merges(
        self,
        *,
        mode: KnowledgePreprocessingMode,
        file_name: str,
        groups: Sequence[KnowledgeSemanticMergeGroup],
        existing_project_titles: Sequence[str] = (),
    ) -> KnowledgeSemanticMergeExecutionResult: ...


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
