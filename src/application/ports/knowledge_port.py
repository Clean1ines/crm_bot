from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from src.application.ports.knowledge.curation import KnowledgeCurationPort
from src.application.ports.knowledge.runtime_search import KnowledgeRuntimeRetrievalPort
from src.domain.control_plane.project_views import ProjectSummaryView
from src.domain.project_plane.knowledge_processing_modes import (
    KnowledgeProcessingMode,
)
from src.domain.project_plane.model_usage_views import (
    ModelUsageEventCreate,
    ModelUsageSummaryView,
)


JsonScalar = str | int | float | bool | None
JsonObject = dict[str, JsonScalar | list[object] | dict[str, object]]
JsonSequence = Sequence[JsonObject]

KnowledgeAnswerResolutionCase = JsonObject
KnowledgeAnswerResolverExecutionResult = object
KnowledgePreprocessingExecutionResult = object
KnowledgePreprocessingMode = KnowledgeProcessingMode


class KnowledgeDbPoolPort(Protocol):
    """Minimal DB pool protocol kept local to avoid importing legacy documents.py.

    Kept local so cleanup repository factories do not import retired
    knowledge port tails or compiler/candidate ports.
    """


class KnowledgeDocumentPort(Protocol):
    """Temporary narrow document marker for the legacy aggregate port.

    Do not add compiler/candidate methods here. New FAQ Workbench code must use
    src.application.ports.knowledge_workbench instead.
    """


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
    "KnowledgeChunkerFactoryPort",
    "KnowledgeChunkerPort",
    "KnowledgeCurationPort",
    "KnowledgeDbPoolPort",
    "KnowledgeDocumentPort",
    "KnowledgePreprocessorFactoryPort",
    "KnowledgePreprocessorPort",
    "KnowledgeProjectAccessPort",
    "KnowledgeQueuePort",
    "KnowledgeRepositoryFactoryPort",
    "KnowledgeRepositoryPort",
    "KnowledgeRuntimeRetrievalPort",
    "ModelUsageRepositoryFactoryPort",
    "ModelUsageRepositoryPort",
    "PlatformUserAdminPort",
]
