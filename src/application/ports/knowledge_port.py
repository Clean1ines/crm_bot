from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

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
from src.domain.project_plane.model_usage_views import (
    ModelUsageEventCreate,
    ModelUsageSummaryView,
)
from src.domain.project_plane.retrieval_surface_compilation import (
    LocalRelationPlanningResult,
    LocalSurfaceRelation,
    RetrievalSurfaceCandidate,
    RetrievalSurfaceCompilationResult,
    RetrievalSurfaceSourceUnit,
    SurfaceAnswerDraft,
    SurfaceDiscoveryResult,
    SurfaceGraphReconciliationResult,
    SurfaceQuestionOwnership,
    SurfaceQuestionOwnershipResult,
    SurfaceRelationClusterContext,
    SurfaceRelationJudgeResult,
)


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
        run_id: str,
    ) -> RetrievalSurfaceCompilationResult: ...


class KnowledgeSurfaceGraphCompilerPort(Protocol):
    @property
    def model_name(self) -> str: ...

    async def discover_surfaces_for_source_unit(
        self,
        *,
        source_unit: RetrievalSurfaceSourceUnit,
        file_name: str,
        run_id: str,
    ) -> SurfaceDiscoveryResult: ...

    async def plan_local_relations(
        self,
        *,
        source_unit: RetrievalSurfaceSourceUnit,
        candidates: Sequence[RetrievalSurfaceCandidate],
        file_name: str,
        run_id: str,
    ) -> LocalRelationPlanningResult: ...

    async def synthesize_surface_answer(
        self,
        *,
        source_unit: RetrievalSurfaceSourceUnit,
        candidate: RetrievalSurfaceCandidate,
        local_relations: Sequence[LocalSurfaceRelation],
        related_candidates: Sequence[RetrievalSurfaceCandidate],
        file_name: str,
        run_id: str,
    ) -> SurfaceAnswerDraft: ...

    async def assign_surface_questions(
        self,
        *,
        source_unit: RetrievalSurfaceSourceUnit,
        answer_draft: SurfaceAnswerDraft,
        candidate: RetrievalSurfaceCandidate,
        local_relations: Sequence[LocalSurfaceRelation],
        related_candidates: Sequence[RetrievalSurfaceCandidate],
        file_name: str,
        run_id: str,
    ) -> SurfaceQuestionOwnershipResult: ...

    async def judge_relation_cluster(
        self,
        *,
        candidates: Sequence[SurfaceAnswerDraft],
        existing_relations: Sequence[LocalSurfaceRelation],
        cluster_context: SurfaceRelationClusterContext,
        run_id: str,
    ) -> SurfaceRelationJudgeResult: ...

    async def reconcile_global_graph(
        self,
        *,
        candidates: Sequence[SurfaceAnswerDraft],
        local_relations: Sequence[LocalSurfaceRelation],
        question_ownership: Sequence[SurfaceQuestionOwnership],
        relation_judgements: Sequence[SurfaceRelationJudgeResult],
        run_id: str,
    ) -> SurfaceGraphReconciliationResult: ...


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
    "KnowledgeSurfaceGraphCompilerPort",
    "ModelUsageRepositoryFactoryPort",
    "ModelUsageRepositoryPort",
    "PlatformUserAdminPort",
]
