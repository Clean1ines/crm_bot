from __future__ import annotations

from collections.abc import Sequence
from src.application.ports.knowledge import (
    KnowledgeAnswerCandidatePort,
    KnowledgeCanonicalEntryPort,
    KnowledgeCompilationTracePort,
    KnowledgeCurationPort,
    KnowledgeDbPoolPort,
    KnowledgeDocumentPort,
    KnowledgeDocumentRuntimeEntries,
    KnowledgeRuntimeRetrievalPort,
    KnowledgeSourceMaterialPort,
)
from src.domain.control_plane.project_views import ProjectSummaryView
from src.domain.project_plane.json_types import JsonObject
from src.domain.project_plane.knowledge_preprocessing import (
    KnowledgeAnswerResolutionCase,
    KnowledgeAnswerResolverExecutionResult,
    KnowledgePreprocessingExecutionResult,
    KnowledgePreprocessingMode,
)
from src.domain.project_plane.retrieval_surface_compilation import (
    RetrievalSurfaceCompilationExecutionResult,
    RetrievalSurfaceSourceUnit,
)
from src.domain.project_plane.model_usage_views import (
    ModelUsageEventCreate,
    ModelUsageSummaryView,
)
from typing import Protocol


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
    ) -> KnowledgePreprocessingExecutionResult: ...

    async def resolve_answer_cases(
        self,
        *,
        mode: KnowledgePreprocessingMode,
        file_name: str,
        cases: Sequence[KnowledgeAnswerResolutionCase],
        existing_project_titles: Sequence[str] = (),
    ) -> KnowledgeAnswerResolverExecutionResult: ...


class KnowledgePreprocessorFactoryPort(Protocol):
    def __call__(self) -> KnowledgePreprocessorPort: ...


class KnowledgeSurfaceCompilerPort(Protocol):
    @property
    def model_name(self) -> str: ...

    async def compile_surfaces(
        self,
        *,
        mode: KnowledgePreprocessingMode,
        source_units: Sequence[RetrievalSurfaceSourceUnit],
        file_name: str,
    ) -> RetrievalSurfaceCompilationExecutionResult: ...


class KnowledgeSurfaceCompilerFactoryPort(Protocol):
    def __call__(self) -> KnowledgeSurfaceCompilerPort: ...


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


class KnowledgeRepositoryPort(
    KnowledgeDocumentPort,
    KnowledgeSourceMaterialPort,
    KnowledgeCompilationTracePort,
    KnowledgeAnswerCandidatePort,
    KnowledgeCanonicalEntryPort,
    KnowledgeRuntimeRetrievalPort,
    KnowledgeCurationPort,
    Protocol,
):
    """Temporary aggregate compatibility port.

    Do not add knowledge-domain methods here. Add them to one bounded-context
    port under src/application/ports/knowledge/ instead.
    """


class KnowledgeRepositoryFactoryPort(Protocol):
    def __call__(self, pool: KnowledgeDbPoolPort) -> KnowledgeRepositoryPort: ...


__all__ = [
    "JwtDecoderPort",
    "KnowledgeAnswerCandidatePort",
    "KnowledgeCanonicalEntryPort",
    "KnowledgeChunkerFactoryPort",
    "KnowledgeChunkerPort",
    "KnowledgeCompilationTracePort",
    "KnowledgeCurationPort",
    "KnowledgeDbPoolPort",
    "KnowledgeDocumentPort",
    "KnowledgeDocumentRuntimeEntries",
    "KnowledgePreprocessorFactoryPort",
    "KnowledgePreprocessorPort",
    "KnowledgeProjectAccessPort",
    "KnowledgeQueuePort",
    "KnowledgeRepositoryFactoryPort",
    "KnowledgeRepositoryPort",
    "KnowledgeRuntimeRetrievalPort",
    "KnowledgeSourceMaterialPort",
    "KnowledgeSurfaceCompilerFactoryPort",
    "KnowledgeSurfaceCompilerPort",
    "ModelUsageRepositoryFactoryPort",
    "ModelUsageRepositoryPort",
    "PlatformUserAdminPort",
]
