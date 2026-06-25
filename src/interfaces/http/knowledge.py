"""
Knowledge extraction API boundary.

This router owns the current upload -> source ingestion -> workflow command drain
vertical. Queue-based FAQ Workbench document upload is retired.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from typing import Protocol, cast
from uuid import UUID
import asyncpg
from fastapi import (
    APIRouter,
    Body,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from starlette.responses import StreamingResponse

from src.domain.commercial.commercial_truth import CommercialTruthResolutionPolicy
from src.domain.project_plane.json_types import JsonObject
from src.contexts.knowledge_workbench.application.sagas.run_source_ingestion_first_phase import (
    RunSourceIngestionFirstPhaseCommand,
)
from src.contexts.knowledge_workbench.application.sagas.source_ingestion_admission import (
    SourceIngestionActor,
    SourceIngestionAdmissionStatus,
)
from src.contexts.knowledge_workbench.application.sagas.pause_knowledge_extraction_workflow import (
    KnowledgeExtractionWorkflowPauseNotFoundError,
    KnowledgeExtractionWorkflowPauseProjectMismatchError,
    KnowledgeExtractionWorkflowPauseTerminalStateError,
    PauseKnowledgeExtractionWorkflowCommand,
)
from src.contexts.knowledge_workbench.application.sagas.resume_knowledge_extraction_workflow import (
    KnowledgeExtractionWorkflowResumeNotPausedError,
    KnowledgeExtractionWorkflowResumeProjectMismatchError,
    KnowledgeExtractionWorkflowResumeStateNotFoundError,
    KnowledgeExtractionWorkflowResumeTerminalStateError,
    ResumeKnowledgeExtractionWorkflowCommand,
)
from src.contexts.knowledge_workbench.application.sagas.delete_knowledge_extraction_document_run import (
    DeleteKnowledgeExtractionDocumentRun,
    DeleteKnowledgeExtractionDocumentRunCommand,
)
from src.contexts.knowledge_workbench.infrastructure.postgres.postgres_workbench_document_run_cleanup_repository import (
    PostgresWorkbenchDocumentRunCleanupRepository,
)
from src.contexts.knowledge_workbench.observability.application.models.frontend_workflow_event import (
    FrontendWorkflowEvent,
)
from src.contexts.knowledge_workbench.observability.application.models.frontend_workflow_event_cursor import (
    FrontendWorkflowEventCursor,
)
from src.contexts.knowledge_workbench.observability.infrastructure.postgres.postgres_frontend_workflow_event_repository import (
    PostgresFrontendWorkflowEventRepository,
)
from src.interfaces.realtime.redis_frontend_workflow_event_bus import (
    subscribe_frontend_workflow_events,
)
from src.contexts.knowledge_workbench.source_management.domain.entities.source_unit import (
    SourceUnit,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_format import (
    SourceFormat,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_document_ref import (
    SourceDocumentRef,
)
from src.contexts.llm_runtime.application.ports.llm_dispatch_executor_port import (
    LlmDispatchExecutorPort,
)
from src.interfaces.composition.knowledge_extraction_after_upload_composition import (
    make_knowledge_extraction_workflow_after_upload,
)
from src.interfaces.composition.knowledge_extraction_workflow_after_upload import (
    RunKnowledgeExtractionWorkflowAfterUploadCommand,
)
from src.interfaces.composition.knowledge_extraction_workflow_pause_resume import (
    make_pause_knowledge_extraction_workflow,
    make_resume_knowledge_extraction_workflow_transition,
)
from src.interfaces.composition.knowledge_extraction_degraded_fallback_confirmation import (
    make_knowledge_extraction_degraded_fallback_confirmation,
)
from src.contexts.knowledge_workbench.application.sagas.confirm_draft_claim_compaction_degraded_fallback import (
    ConfirmDraftClaimCompactionDegradedFallbackCommand,
    DraftClaimCompactionDegradedFallbackNotPendingError,
)
from src.interfaces.composition.knowledge_extraction_workflow_resume import (
    KnowledgeExtractionWorkflowResumeNotFoundError,
    RunKnowledgeExtractionWorkflowResumeCommand,
    make_knowledge_extraction_workflow_resume,
)
from src.interfaces.composition.faq_workbench_workflow_live_state import (
    WorkbenchWorkflowLiveStateNotFoundError,
    fetch_workbench_workflow_live_state,
)
from src.infrastructure.config.settings import settings
from src.contexts.knowledge_workbench.extraction.application.ports.draft_claim_observation_read_repository_port import (
    DraftClaimObservationReadModel,
    DraftClaimObservationReadRepositoryPort,
)
from src.contexts.knowledge_workbench.extraction.infrastructure.postgres.postgres_draft_claim_observation_read_repository import (
    DraftClaimObservationReadConnectionLike,
    PostgresDraftClaimObservationReadRepository,
)
from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_models import (
    DraftClaimCompactionBatchReadModel,
    DraftClaimCompactionGroupMemberReadModel,
    DraftClaimCompactionGroupReadModel,
)
from src.contexts.knowledge_workbench.extraction.infrastructure.postgres.postgres_draft_claim_compaction_plan_repository import (
    PostgresDraftClaimCompactionPlanRepository,
)
from src.contexts.knowledge_workbench.source_management.application.ports.source_management_repository_port import (
    SourceManagementRepositoryPort,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_saga_ports import (
    KnowledgeExtractionSagaStateRepositoryPort,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalCommandType,
)
from src.contexts.workflow_runtime.domain.entities.workflow_command import (
    WorkflowCommand,
    WorkflowCommandStatus,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_command_id import (
    WorkflowCommandId,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_idempotency_key import (
    WorkflowIdempotencyKey,
)
from src.contexts.workflow_runtime.infrastructure.postgres.postgres_workflow_runtime_unit_of_work import (
    PostgresWorkflowRuntimeUnitOfWork,
)
from src.contexts.knowledge_workbench.source_management.infrastructure.postgres.postgres_source_management_repository import (
    AsyncSourceManagementConnectionLike,
    PostgresSourceManagementRepository,
)
from src.contexts.knowledge_workbench.curation.application.ports.draft_claim_curation_workspace_repository_port import (
    DraftClaimCurationWorkspaceRepositoryPort,
)
from src.contexts.knowledge_workbench.curation.application.use_cases.read_draft_claim_curation_workspace import (
    ReadDraftClaimCurationWorkspace,
)
from src.contexts.knowledge_workbench.curation.infrastructure.postgres.postgres_draft_claim_curation_workspace_repository import (
    DraftClaimCurationWorkspaceConnectionLike,
    PostgresDraftClaimCurationWorkspaceRepository,
)
from src.contexts.knowledge_workbench.extraction.application.ports.draft_claim_compaction_reduction_state_repository_port import (
    DraftClaimCompactionReductionStateRepositoryPort,
)
from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_reduction_models import (
    DraftClaimCompactionFrontierReadModel,
    DraftClaimCompactionFrontierNodeReadModel,
    DraftClaimCompactionNodeReadModel,
    DraftClaimCompactionPendingReductionWorkReadModel,
)
from src.contexts.knowledge_workbench.extraction.infrastructure.postgres.postgres_draft_claim_compaction_reduction_state_repository import (
    DraftClaimCompactionReductionStateConnectionLike,
    PostgresDraftClaimCompactionReductionStateRepository,
)
from src.contexts.knowledge_workbench.infrastructure.postgres.postgres_knowledge_extraction_saga_state_repository import (
    AsyncKnowledgeExtractionSagaConnectionLike,
    PostgresKnowledgeExtractionSagaStateRepository,
)
from src.contexts.knowledge_workbench.curation.application.use_cases.open_draft_claim_curation_workspace import (
    DraftClaimCurationWorkspaceOpenError,
    DraftClaimCurationWorkspaceProjectMismatchError,
    OpenDraftClaimCurationWorkspace,
)
from src.contexts.knowledge_workbench.curation.application.use_cases.ensure_draft_claim_curation_workflow_project import (
    DraftClaimCurationWorkflowNotFoundError,
    DraftClaimCurationWorkflowProjectMismatchError,
    EnsureDraftClaimCurationWorkflowProject,
)
from src.contexts.knowledge_workbench.curation.application.use_cases.set_draft_claim_curation_item_excluded import (
    DraftClaimCurationItemExclusionError,
    SetDraftClaimCurationItemExcluded,
)
from src.contexts.knowledge_workbench.curation.application.use_cases.update_draft_claim_curation_item import (
    DraftClaimCurationItemUpdateError,
    UpdateDraftClaimCurationItem,
)
from src.contexts.knowledge_workbench.curation.application.use_cases.publish_draft_claim_curation_workspace import (
    DraftClaimCurationPublicationAlreadyPublishedError,
    DraftClaimCurationPublicationEmbeddingError,
    DraftClaimCurationPublicationEmptyError,
    DraftClaimCurationPublicationNotFoundError,
    PublishDraftClaimCurationWorkspace,
)
from src.contexts.knowledge_workbench.rag_eval.infrastructure.postgres.postgres_workbench_rag_eval_repository import (
    PostgresWorkbenchRagEvalRepository,
)
from src.contexts.knowledge_workbench.rag_eval.application.errors.workbench_rag_eval_question_generation_errors import (
    WorkbenchRagEvalDegradedFallbackRequiredError,
    WorkbenchRagEvalQuestionGenerationError,
)
from src.contexts.knowledge_workbench.rag_eval.application.use_cases.apply_workbench_rag_eval_promotion import (
    WorkbenchRagEvalPromotionConflictError,
    WorkbenchRagEvalPromotionEmbeddingError,
    WorkbenchRagEvalPromotionNotFoundError,
)
from src.infrastructure.db.repositories.user_repository import UserRepository
from src.infrastructure.logging.logger import get_logger
from src.interfaces.http.dependencies import (
    get_llm_dispatch_executor,
    get_pool,
    get_project_repo,
    get_user_repository,
)

logger = get_logger(__name__)


class AsyncPool(Protocol):
    async def acquire(self) -> object: ...

    async def release(self, connection: object) -> None: ...


router = APIRouter(prefix="/api/projects/{project_id}/knowledge", tags=["knowledge"])

UPLOAD_TOO_LARGE_DETAIL = "Knowledge upload file is too large"
_SOURCE_UNIT_TEXT_PREVIEW_LIMIT = 500


class _WorkbenchDocumentListConnection(Protocol):
    async def fetch(self, query: str, *args: object) -> list[Mapping[str, object]]: ...


class _WorkbenchDocumentListAcquireContext(Protocol):
    async def __aenter__(self) -> _WorkbenchDocumentListConnection: ...

    async def __aexit__(
        self,
        exc_type: object,
        exc: object,
        traceback: object,
    ) -> bool | None: ...


class _WorkbenchDocumentListPool(Protocol):
    def acquire(self) -> _WorkbenchDocumentListAcquireContext: ...


async def _maybe_await(value: object) -> object:
    import inspect

    if inspect.isawaitable(value):
        return await value
    return value


_ALLOWED_WORKBENCH_UPLOAD_EXTENSIONS = frozenset(
    {".txt", ".md", ".markdown", ".pdf", ".json"}
)


def _validate_workbench_upload_file_name(file_name: str | None) -> None:
    normalized = (file_name or "").strip()
    if not normalized:
        return

    if "." not in normalized:
        return

    suffix = "." + normalized.rsplit(".", 1)[-1].lower()
    if suffix not in _ALLOWED_WORKBENCH_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {normalized}",
        )


async def _project_exists_for_workbench(project_repo: object, project_id: str) -> bool:
    project_exists = getattr(project_repo, "project_exists", None)
    if project_exists is not None:
        return bool(await _maybe_await(project_exists(project_id)))

    get_project_view = getattr(project_repo, "get_project_view", None)
    if get_project_view is not None:
        return await _maybe_await(get_project_view(project_id)) is not None

    return True


async def _user_is_platform_admin_for_workbench(
    user_repo: UserRepository,
    user_id: str,
) -> bool:
    is_platform_admin = getattr(user_repo, "is_platform_admin", None)
    if is_platform_admin is None:
        return False
    return bool(await _maybe_await(is_platform_admin(user_id)))


async def _user_has_workbench_project_role(
    project_repo: object,
    *,
    project_id: str,
    user_id: str,
) -> bool:
    user_has_project_role = getattr(project_repo, "user_has_project_role", None)
    if user_has_project_role is None:
        return False

    allowed_roles = ("owner", "admin", "manager")

    try:
        return bool(
            await _maybe_await(
                user_has_project_role(project_id, user_id, allowed_roles)
            )
        )
    except TypeError:
        return bool(
            await _maybe_await(
                user_has_project_role(
                    project_id=project_id,
                    user_id=user_id,
                    allowed_roles=allowed_roles,
                )
            )
        )


async def _read_upload_bytes(file: UploadFile) -> bytearray:
    buffer = bytearray()
    max_bytes = settings.KNOWLEDGE_UPLOAD_MAX_BYTES
    chunk_size = settings.KNOWLEDGE_UPLOAD_READ_CHUNK_BYTES

    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            return buffer

        buffer.extend(chunk)
        if len(buffer) > max_bytes:
            raise HTTPException(status_code=413, detail=UPLOAD_TOO_LARGE_DETAIL)


def _decode_workbench_upload_text(file_content: bytes | bytearray) -> str:
    try:
        text = bytes(file_content).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=400,
            detail="Knowledge upload must be UTF-8 text for source ingestion v1",
        ) from exc

    if not text.strip():
        raise HTTPException(status_code=400, detail="Knowledge upload text is empty")

    return text


async def _build_source_ingestion_actor(
    *,
    authorization: str | None,
    user_repo: UserRepository,
) -> SourceIngestionActor:
    from src.interfaces.http.dependencies import get_current_user_id

    user_id = await get_current_user_id(authorization)
    is_platform_admin = getattr(user_repo, "is_platform_admin", None)
    platform_admin = False
    if is_platform_admin is not None:
        platform_admin = bool(await _maybe_await(is_platform_admin(user_id)))

    return SourceIngestionActor(
        actor_user_id=user_id,
        is_platform_admin=platform_admin,
    )


def _source_format_from_upload_name(file_name: str | None) -> SourceFormat:
    normalized = (file_name or "").strip().lower()
    suffix = ""
    if "." in normalized:
        suffix = "." + normalized.rsplit(".", 1)[-1]

    if suffix in {".md", ".markdown"}:
        return SourceFormat.MARKDOWN
    if suffix == ".pdf":
        return SourceFormat.PDF
    if suffix == ".html":
        return SourceFormat.HTML
    if suffix in {".txt", ".json"}:
        return SourceFormat.PLAIN_TEXT
    return SourceFormat.PLAIN_TEXT


def _raise_source_ingestion_rejected(
    admission_status: SourceIngestionAdmissionStatus,
) -> None:
    if admission_status is SourceIngestionAdmissionStatus.PROJECT_NOT_FOUND:
        raise HTTPException(status_code=404, detail=admission_status.value)
    if admission_status is SourceIngestionAdmissionStatus.ACTOR_NOT_AUTHENTICATED:
        raise HTTPException(status_code=401, detail=admission_status.value)
    raise HTTPException(status_code=403, detail=admission_status.value)


def _optional_datetime_isoformat(value: object) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    return None


def _jsonable(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {key: _jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    enum_value = getattr(value, "value", None)
    if isinstance(enum_value, str):
        return enum_value
    return value


def _source_unit_read_model(unit: SourceUnit) -> dict[str, object]:
    text = unit.text.value
    return {
        "source_unit_ref": unit.unit_ref.value,
        "ordinal": unit.ordinal,
        "unit_kind": unit.unit_kind.name,
        "heading_path": list(unit.heading_path.parts),
        "text_preview": text[:_SOURCE_UNIT_TEXT_PREVIEW_LIMIT],
        "text_length": len(text),
        "created_at": unit.created_at.isoformat(),
    }


def _document_card_lifecycle_state(status: object) -> str:
    normalized = str(status or "").strip().lower()
    if normalized in {"processing", "pending"}:
        return "processing"
    if normalized in {"cancelled", "canceled", "cancelled_by_user"}:
        return "cancelled"
    if normalized in {"error", "failed"}:
        return "failed"
    if normalized in {"processed", "completed", "done"}:
        return "ready"
    return "processing"


def _workbench_document_card_view_fallback(
    document: Mapping[str, object],
) -> dict[str, object]:
    document_id = str(document["document_id"])
    project_id = str(document["project_id"])
    file_name = str(document["file_name"])
    status = str(document.get("status") or "processing")
    lifecycle_state = _document_card_lifecycle_state(status)
    raw_source_unit_count = document.get("source_unit_count")
    source_unit_count = (
        raw_source_unit_count
        if isinstance(raw_source_unit_count, int)
        and not isinstance(raw_source_unit_count, bool)
        else 0
    )
    running = lifecycle_state == "processing"

    return {
        "document_id": document_id,
        "project_id": project_id,
        "file_name": file_name,
        "source_type": "source_ingestion",
        "lifecycle_state": lifecycle_state,
        "retention_state": "retained",
        "transient_purged": False,
        "resume_available": False,
        "status_i18n_key": f"knowledge.workbench.status.{lifecycle_state}",
        "default_status_label": (
            "Обрабатывается"
            if running
            else "Остановлено"
            if lifecycle_state == "cancelled"
            else "Ошибка"
            if lifecycle_state == "failed"
            else "Готово"
        ),
        "status_description_i18n_key": (
            "knowledge.workbench.description.sourceIngestion"
        ),
        "default_status_description": (
            "Документ принят в source-ingestion pipeline. Live-state показывает текущие стадии обработки."
            if running
            else "Обработка документа остановлена."
            if lifecycle_state == "cancelled"
            else "Обработка документа завершилась ошибкой."
            if lifecycle_state == "failed"
            else "Документ обработан."
        ),
        "timer": {
            "mode": "running" if running else "stopped",
            "active_elapsed_seconds": 0,
            "wall_elapsed_seconds": 0,
            "current_active_started_at": (
                _optional_datetime_isoformat(document.get("updated_at"))
                if running
                else None
            ),
            "i18n_key": "knowledge.workbench.timer.processing",
            "default_label": "Время",
        },
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "llm_call_count": 0,
            "i18n_key": "knowledge.workbench.usage.pending",
        },
        "sections": {
            "total": source_unit_count,
            "processed": 0,
            "failed": 0,
            "pending": source_unit_count,
        },
        "registry": {
            "entry_count": 0,
            "final_snapshot_id": None,
            "retained": True,
        },
        "surfaces": {
            "draft_count": 0,
            "ready_count": 0,
            "published_count": 0,
            "rejected_count": 0,
        },
        "runtime": {
            "publication_id": None,
            "runtime_entry_count": 0,
        },
        "recovery": {
            "mode": "none",
            "scheduled_at": None,
            "can_cancel_scheduled_resume": False,
            "reason_code": "none",
            "i18n_key": "knowledge.workbench.recovery.none",
            "default_message": "Автовосстановление не запланировано",
        },
        "actions": [
            {
                "action_id": "cancel_processing",
                "visible": running,
                "enabled": running,
                "tone": "danger",
                "i18n_key": "knowledge.actions.stop",
                "default_label": "Остановить",
                "reason_code": None if running else "not_running",
                "confirmation_i18n_key": None,
                "default_confirmation": "Остановить обработку документа?",
            },
            {
                "action_id": "delete_document",
                "visible": True,
                "enabled": True,
                "tone": "danger",
                "i18n_key": "knowledge.actions.delete",
                "default_label": "Удалить",
                "reason_code": None,
                "confirmation_i18n_key": None,
                "default_confirmation": "Удалить документ и связанные артефакты?",
            },
        ],
        "messages": [],
        "error": None,
        "metadata": {
            "workbench_phase": {
                "source_unit_count": source_unit_count,
                "prompt_a_completed_sections": 0,
                "section_queue_ready_count": 0,
                "section_queue_leased_count": 0,
                "registry_application_ready_count": 0,
                "registry_application_leased_count": 0,
            },
            "workbench_claim_preview_count": 0,
            "workbench_claim_preview": [],
        },
    }


async def _list_workbench_documents_fallback(
    *,
    pool: object,
    project_id: str,
    limit: int,
    offset: int,
) -> dict[str, object]:
    async with cast(_WorkbenchDocumentListPool, pool).acquire() as connection:
        rows = await connection.fetch(
            """
            SELECT
                document_id,
                project_id::text AS project_id,
                file_name,
                status,
                created_at,
                updated_at,
                current_processing_run_id,
                file_size_bytes,
                COALESCE(
                    (
                        SELECT COUNT(*)::int
                        FROM source_units AS su
                        WHERE su.document_ref = document_id
                    ),
                    0
                ) AS source_unit_count
            FROM knowledge_workbench_documents
            WHERE project_id = $1
              AND deleted_at IS NULL
            ORDER BY created_at DESC, document_id DESC
            LIMIT $2 OFFSET $3
            """,
            project_id,
            limit,
            offset,
        )

    documents: list[dict[str, object]] = []
    for row in rows:
        document = dict(row)
        created_at = document.get("created_at")
        updated_at = document.get("updated_at")
        documents.append(
            {
                "id": document["document_id"],
                "document_id": document["document_id"],
                "project_id": document["project_id"],
                "file_name": document["file_name"],
                "status": document["status"],
                "file_size": document.get("file_size_bytes", 0),
                "created_at": (_optional_datetime_isoformat(created_at)),
                "updated_at": (_optional_datetime_isoformat(updated_at)),
                "current_processing_run_id": document.get("current_processing_run_id"),
                "card_view": _workbench_document_card_view_fallback(document),
            }
        )

    return {
        "documents": documents,
        "items": documents,
        "limit": limit,
        "offset": offset,
        "count": len(documents),
    }


def _source_units_url(
    *,
    project_id: str,
    source_document_ref: str,
) -> str:
    return (
        f"/api/projects/{project_id}/knowledge/source-documents/"
        f"{source_document_ref}/source-units"
    )


def _source_document_draft_claims_url(
    *,
    project_id: str,
    source_document_ref: str,
) -> str:
    return (
        f"/api/projects/{project_id}/knowledge/source-documents/"
        f"{source_document_ref}/draft-claims"
    )


def _curation_workspace_repositories(
    pool: object,
) -> tuple[
    DraftClaimCurationWorkspaceRepositoryPort,
    DraftClaimCompactionReductionStateRepositoryPort,
    DraftClaimObservationReadRepositoryPort,
    SourceManagementRepositoryPort,
    KnowledgeExtractionSagaStateRepositoryPort,
]:
    curation_repository: DraftClaimCurationWorkspaceRepositoryPort = (
        PostgresDraftClaimCurationWorkspaceRepository(
            cast(DraftClaimCurationWorkspaceConnectionLike, pool)
        )
    )
    compaction_repository: DraftClaimCompactionReductionStateRepositoryPort = (
        PostgresDraftClaimCompactionReductionStateRepository(
            cast(DraftClaimCompactionReductionStateConnectionLike, pool)
        )
    )
    draft_claim_repository: DraftClaimObservationReadRepositoryPort = (
        PostgresDraftClaimObservationReadRepository(
            cast(DraftClaimObservationReadConnectionLike, pool)
        )
    )
    source_repository: SourceManagementRepositoryPort = (
        PostgresSourceManagementRepository(
            cast(AsyncSourceManagementConnectionLike, pool)
        )
    )
    saga_state_repository: KnowledgeExtractionSagaStateRepositoryPort = (
        PostgresKnowledgeExtractionSagaStateRepository(
            cast(AsyncKnowledgeExtractionSagaConnectionLike, pool)
        )
    )
    return (
        curation_repository,
        compaction_repository,
        draft_claim_repository,
        source_repository,
        saga_state_repository,
    )


async def _ensure_curation_workflow_project(
    *,
    workflow_run_id: str,
    project_id: str,
    saga_state_repository: KnowledgeExtractionSagaStateRepositoryPort,
):
    try:
        return await EnsureDraftClaimCurationWorkflowProject(
            state_repository=saga_state_repository,
        ).execute(
            workflow_run_id=workflow_run_id,
            expected_project_id=project_id,
        )
    except (
        DraftClaimCurationWorkflowNotFoundError,
        DraftClaimCurationWorkflowProjectMismatchError,
    ) as exc:
        raise HTTPException(status_code=404, detail="Workflow not found") from exc


async def _read_curation_workspace_response(
    *,
    workflow_run_id: str,
    curation_repository: DraftClaimCurationWorkspaceRepositoryPort,
    compaction_repository: DraftClaimCompactionReductionStateRepositoryPort,
    draft_claim_repository: DraftClaimObservationReadRepositoryPort,
    source_repository: SourceManagementRepositoryPort,
) -> JsonObject:
    result = await ReadDraftClaimCurationWorkspace(
        curation_workspace_repository=curation_repository,
        compaction_reduction_state_repository=compaction_repository,
        draft_claim_observation_read_repository=draft_claim_repository,
        source_management_repository=source_repository,
    ).execute(workflow_run_id=workflow_run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Curation workspace not found")
    return result.to_json_dict()


def _draft_claim_observation_read_model(
    item: DraftClaimObservationReadModel,
) -> dict[str, object]:
    return {
        "observation_ref": item.observation_ref,
        "source_unit_ref": item.source_unit_ref,
        "claim": item.claim,
        "granularity": item.granularity,
        "possible_questions": list(item.possible_questions),
        "exclusion_scope": item.exclusion_scope,
        "evidence_block": item.evidence_block,
        "provenance": {
            "workflow_run_id": item.workflow_run_id,
            "stage_run_id": item.stage_run_id,
            "work_item_id": item.work_item_id,
            "work_item_attempt_id": item.work_item_attempt_id,
            "llm_task_id": item.llm_task_id,
            "llm_attempt_id": item.llm_attempt_id,
            "prompt_id": item.prompt_id,
            "prompt_version": item.prompt_version,
            "claim_index": item.claim_index,
        },
        "created_at": item.created_at.isoformat(),
    }


def _derived_compaction_work_item_id(*, workflow_run_id: str, batch_ref: str) -> str:
    return f"claim-compaction:{workflow_run_id}:{batch_ref}"


def _draft_claim_compaction_node_read_model(
    item: DraftClaimCompactionNodeReadModel,
) -> dict[str, object]:
    return {
        "node_ref": item.node_ref,
        "workflow_run_id": item.workflow_run_id,
        "group_ref": item.group_ref,
        "node_kind": item.node_kind,
        "active": item.active,
        "source_claim_refs": list(item.source_claim_refs),
        "source_claim_count": len(item.source_claim_refs),
        "supersedes_node_refs": list(item.supersedes_node_refs),
        "supersedes_node_count": len(item.supersedes_node_refs),
        "estimated_input_tokens": item.estimated_input_tokens,
        "compacted_key": item.compacted_key,
        "compacted_claim": item.compacted_claim,
        "compacted_claim_kind": item.compacted_claim_kind,
        "compacted_granularity": item.compacted_granularity,
        "compacted_merge_decision": item.compacted_merge_decision,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
    }


def _draft_claim_compaction_frontier_node_read_model(
    item: DraftClaimCompactionFrontierNodeReadModel,
) -> dict[str, object]:
    return {
        "node_ref": item.node_ref,
        "workflow_run_id": item.workflow_run_id,
        "group_ref": item.group_ref,
        "node_kind": item.node_kind,
        "active": item.active,
        "frontier_state": item.frontier_state,
        "source_claim_refs": list(item.source_claim_refs),
        "source_claim_count": item.source_claim_count,
        "supersedes_node_refs": list(item.supersedes_node_refs),
        "supersedes_node_count": item.supersedes_node_count,
        "estimated_input_tokens": item.estimated_input_tokens,
        "compacted_key": item.compacted_key,
        "compacted_claim": item.compacted_claim,
        "compacted_claim_kind": item.compacted_claim_kind,
        "compacted_granularity": item.compacted_granularity,
        "compacted_merge_decision": item.compacted_merge_decision,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
    }


def _draft_claim_compaction_pending_work_read_model(
    item: DraftClaimCompactionPendingReductionWorkReadModel,
) -> dict[str, object]:
    return {
        "workflow_run_id": item.workflow_run_id,
        "group_ref": item.group_ref,
        "batch_ref": item.batch_ref,
        "work_item_id": item.work_item_id,
        "input_node_refs": list(item.input_node_refs),
        "input_claim_refs": list(item.input_claim_refs),
        "work_item_status": item.work_item_status,
        "dispatch_attempt_id": item.dispatch_attempt_id,
        "capacity_window_key": item.capacity_window_key,
        "capacity_waiting": item.capacity_waiting,
        "provider": item.provider,
        "account_ref": item.account_ref,
        "model_id": item.model_id,
        "waiting_reason": item.waiting_reason,
        "created_at": item.created_at.isoformat()
        if item.created_at is not None
        else None,
        "updated_at": item.updated_at.isoformat()
        if item.updated_at is not None
        else None,
    }


def _draft_claim_compaction_frontier_read_model(
    item: DraftClaimCompactionFrontierReadModel,
    *,
    limit: int,
    offset: int,
    include_inactive: bool,
) -> dict[str, object]:
    return {
        "workflow_run_id": item.workflow_run_id,
        "group_ref": item.group_ref,
        "include_inactive": include_inactive,
        "count": len(item.rows),
        "limit": limit,
        "offset": offset,
        "summary": {
            "workflow_run_id": item.summary.workflow_run_id,
            "group_ref": item.summary.group_ref,
            "group_count": item.summary.group_count,
            "active_raw_count": item.summary.active_raw_count,
            "active_compacted_count": item.summary.active_compacted_count,
            "inactive_node_count": item.summary.inactive_node_count,
            "superseded_node_count": item.summary.superseded_node_count,
            "total_node_count": item.summary.total_node_count,
            "group_done_count": item.summary.group_done_count,
            "all_groups_compacted": item.summary.all_groups_compacted,
        },
        "separation_summary": {
            "edge_count": item.separation_summary.edge_count,
            "origin_count": item.separation_summary.origin_count,
            "affected_active_node_count": (
                item.separation_summary.affected_active_node_count
            ),
            "sample_origin_pairs": [
                list(pair) for pair in item.separation_summary.sample_origin_pairs
            ],
        },
        "pending_work_summary": {
            "pending_work_item_count": item.pending_work_summary.pending_work_item_count,
            "leased_or_running_count": item.pending_work_summary.leased_or_running_count,
            "waiting_for_capacity_count": (
                item.pending_work_summary.waiting_for_capacity_count
            ),
            "next_work_scheduled_count": (
                item.pending_work_summary.next_work_scheduled_count
            ),
        },
        "rows": [
            _draft_claim_compaction_frontier_node_read_model(row) for row in item.rows
        ],
        "pending_work_items": [
            _draft_claim_compaction_pending_work_read_model(row)
            for row in item.pending_work_items
        ],
    }


def _draft_claim_cluster_batch_read_model(
    item: DraftClaimCompactionBatchReadModel,
) -> dict[str, object]:
    return {
        "batch_ref": item.batch_ref,
        "group_ref": item.group_ref,
        "workflow_run_id": item.workflow_run_id,
        "prompt_variant": item.prompt_variant,
        "model_id": item.model_id,
        "estimated_input_tokens": item.estimated_input_tokens,
        "batch_status": item.batch_status,
        "member_count": item.member_count,
        "derived_work_item_id": _derived_compaction_work_item_id(
            workflow_run_id=item.workflow_run_id,
            batch_ref=item.batch_ref,
        ),
        "created_at": item.created_at.isoformat(),
    }


def _draft_claim_cluster_group_read_model(
    item: DraftClaimCompactionGroupReadModel,
    *,
    batches: tuple[DraftClaimCompactionBatchReadModel, ...],
) -> dict[str, object]:
    return {
        "group_ref": item.group_ref,
        "workflow_run_id": item.workflow_run_id,
        "source_document_ref": item.source_document_ref,
        "embedding_model_id": item.embedding_model_id,
        "group_algorithm": item.group_algorithm,
        "group_threshold": item.group_threshold,
        "member_count": item.member_count,
        "estimated_input_tokens": item.estimated_input_tokens,
        "requires_split": item.requires_split,
        "created_at": item.created_at.isoformat(),
        "batches": [_draft_claim_cluster_batch_read_model(batch) for batch in batches],
    }


def _draft_claim_cluster_member_read_model(
    item: DraftClaimCompactionGroupMemberReadModel,
) -> dict[str, object]:
    return {
        "group_ref": item.group_ref,
        "observation_ref": item.observation_ref,
        "embedding_ref": item.embedding_ref,
        "source_unit_ref": item.source_unit_ref,
        "member_rank": item.member_rank,
        "member_kind": item.member_kind,
        "created_at": item.created_at.isoformat(),
    }


def _normalize_optional_query_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped if stripped else None


def _require_workflow_draft_claim_scope_filter(
    *,
    source_unit_ref: str | None,
    work_item_id: str | None,
    dispatch_attempt_id: str | None,
) -> None:
    if not any(
        filter_value is not None
        for filter_value in (
            source_unit_ref,
            work_item_id,
            dispatch_attempt_id,
        )
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "At least one of source_unit_ref, work_item_id, "
                "dispatch_attempt_id is required"
            ),
        )


async def _require_project_access(
    *,
    project_id: str,
    authorization: str | None,
    project_repo: object,
    user_repo: UserRepository,
) -> None:
    """Fail-closed Workbench project access.

    The boundary uses the shared HTTP auth dependency and project/user
    repositories directly. It must not expose local JWT patch points or route
    upload authorization through the retired KnowledgeService facade.
    """

    from src.interfaces.http.dependencies import get_current_user_id

    current_user_id = await get_current_user_id(authorization)

    if not await _project_exists_for_workbench(project_repo, project_id):
        raise HTTPException(status_code=404, detail="Project not found")

    if await _user_is_platform_admin_for_workbench(user_repo, current_user_id):
        return

    if await _user_has_workbench_project_role(
        project_repo,
        project_id=project_id,
        user_id=current_user_id,
    ):
        return

    for method_name in (
        "require_project_access",
        "ensure_project_access",
        "require_access",
    ):
        method = getattr(project_repo, method_name, None)
        if method is None:
            continue

        try:
            result = await _maybe_await(method(project_id, authorization))
        except TypeError:
            try:
                result = await _maybe_await(
                    method(
                        project_id=project_id,
                        authorization=authorization,
                    )
                )
            except TypeError:
                continue

        if result is False:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return

    raise HTTPException(status_code=403, detail="Insufficient permissions")


def _legacy_endpoint_gone(*, capability: str, target: str) -> None:
    raise HTTPException(
        status_code=410,
        detail={
            "status": "removed_legacy_knowledge_endpoint",
            "capability": capability,
            "target": target,
            "message": (
                "This endpoint belonged to the old knowledge workflow. "
                "Reintroduce it only as a Workbench read model, Workbench command, "
                "or a separate bounded context."
            ),
        },
    )


def _optional_payload_str(payload: Mapping[str, object], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise HTTPException(status_code=400, detail=f"{key} must be string or null")
    stripped = value.strip()
    return stripped or None


def _optional_payload_int(payload: Mapping[str, object], key: str) -> int | None:
    value = payload.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise HTTPException(status_code=400, detail=f"{key} must be integer")
    return value


def _payload_text(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise HTTPException(status_code=400, detail=f"{key} must be non-empty string")
    return value.strip()


def _optional_payload_text(payload: Mapping[str, object], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise HTTPException(status_code=400, detail=f"{key} must be string or null")
    stripped = value.strip()
    return stripped or None


def _payload_text_tuple(
    payload: Mapping[str, object],
    key: str,
    *,
    default: tuple[str, ...],
) -> tuple[str, ...]:
    value = payload.get(key)
    if value is None:
        return default
    if not isinstance(value, list):
        raise HTTPException(status_code=400, detail=f"{key} must be an array")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise HTTPException(
                status_code=400,
                detail=f"{key} must contain non-empty strings",
            )
        result.append(item.strip())
    return tuple(result)


def _payload_int(payload: Mapping[str, object], key: str, *, default: int) -> int:
    value = _optional_payload_int(payload, key)
    return default if value is None else value


def _payload_bool(payload: Mapping[str, object], key: str, *, default: bool) -> bool:
    value = payload.get(key)
    if value is None:
        return default
    if not isinstance(value, bool):
        raise HTTPException(status_code=400, detail=f"{key} must be boolean")
    return value


@router.get("")
async def list_knowledge_documents(
    project_id: str,
    authorization: str | None = Header(default=None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
):
    """Lists FAQ Workbench documents for a project."""

    await _require_project_access(
        project_id=project_id,
        authorization=authorization,
        project_repo=project_repo,
        user_repo=user_repo,
    )

    return await _list_workbench_documents_fallback(
        pool=pool,
        project_id=project_id,
        limit=limit,
        offset=offset,
    )


@router.post("")
async def upload_knowledge(
    project_id: str,
    file: UploadFile = File(...),
    preprocessing_mode: str = Form(default="faq"),
    authorization: str | None = Header(default=None),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
    llm_executor: LlmDispatchExecutorPort = Depends(get_llm_dispatch_executor),
):
    """Uploads UTF-8 text into the source ingestion first-phase workflow."""

    _validate_workbench_upload_file_name(file.filename)

    try:
        file_content = await _read_upload_bytes(file)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Failed to read uploaded file: {exc}")
        raise HTTPException(status_code=400, detail="Could not read file") from exc

    from src.domain.project_plane.knowledge_processing_modes import (
        KnowledgeProcessingModeValidationError,
        require_faq_workbench_mode,
    )

    try:
        require_faq_workbench_mode(preprocessing_mode)
    except KnowledgeProcessingModeValidationError as exc:
        raise HTTPException(
            status_code=400,
            detail=(
                "Unsupported preprocessing_mode. "
                "Only FAQ Workbench uploads are supported by this endpoint."
            ),
        ) from exc

    raw_text = _decode_workbench_upload_text(file_content)
    actor = await _build_source_ingestion_actor(
        authorization=authorization,
        user_repo=user_repo,
    )
    source_format = _source_format_from_upload_name(file.filename)

    workflow_runner = make_knowledge_extraction_workflow_after_upload(
        pool=pool,
        project_repo=project_repo,
        user_repo=user_repo,
        llm_executor=llm_executor,
    )

    try:
        result = await workflow_runner.execute(
            RunKnowledgeExtractionWorkflowAfterUploadCommand(
                source_ingestion_command=RunSourceIngestionFirstPhaseCommand(
                    project_id=project_id,
                    actor=actor,
                    original_filename=file.filename,
                    source_format=source_format,
                    content_bytes=bytes(file_content),
                    raw_text=raw_text,
                    occurred_at=datetime.now(timezone.utc),
                ),
                max_drain_commands=10,
            )
        )
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not result.source_ingestion_completed:
        admission_status = result.source_ingestion_admission_status
        if admission_status is None:
            raise HTTPException(
                status_code=500,
                detail="Source ingestion rejected without admission status",
            )
        _raise_source_ingestion_rejected(admission_status)

    source_document_ref = result.source_document_ref
    if source_document_ref is None:
        raise HTTPException(
            status_code=500,
            detail="Source ingestion completed without source_document_ref",
        )

    return {
        "status": "knowledge_extraction_workflow_started",
        "workflow_run_id": result.workflow_run_id,
        "source_ingestion_completed": result.source_ingestion_completed,
        "drained_inspected_count": result.drained_inspected_count,
        "drained_dispatched_count": result.drained_dispatched_count,
        "blocked_command_type": result.blocked_command_type,
        "blocked_reason": result.blocked_reason,
        "source_document_ref": source_document_ref,
        "source_unit_count": result.source_unit_count,
        "source_units_url": _source_units_url(
            project_id=project_id,
            source_document_ref=source_document_ref,
        ),
        "draft_claims_url": _source_document_draft_claims_url(
            project_id=project_id,
            source_document_ref=source_document_ref,
        ),
    }


@router.get("/source-documents/{source_document_ref}/source-units")
async def source_ingestion_source_units(
    project_id: str,
    source_document_ref: str,
    authorization: str | None = Header(default=None),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
):
    """Returns persisted source units created by source ingestion first phase."""

    await _require_project_access(
        project_id=project_id,
        authorization=authorization,
        project_repo=project_repo,
        user_repo=user_repo,
    )

    document_ref = SourceDocumentRef(source_document_ref)
    repository = PostgresSourceManagementRepository(pool)
    source_units = await repository.list_source_units_for_document(document_ref)

    return {
        "project_id": project_id,
        "source_document_ref": document_ref.value,
        "source_unit_count": len(source_units),
        "source_units": [_source_unit_read_model(unit) for unit in source_units],
    }


@router.get(
    "/source-documents/{document_id}/workflows/{workflow_run_id}/frontend-events"
)
async def list_knowledge_frontend_workflow_events(
    project_id: str,
    document_id: str,
    workflow_run_id: str,
    after_cursor: str | None = Query(default=None),
    after_source_sequence: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=200),
    authorization: str | None = Header(default=None),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
) -> dict[str, object]:
    """Returns projection-only workflow events for one document workflow."""

    await _require_project_access(
        project_id=project_id,
        authorization=authorization,
        project_repo=project_repo,
        user_repo=user_repo,
    )

    try:
        cursor = _resolve_frontend_workflow_event_cursor(
            after_cursor=after_cursor,
            after_source_sequence=after_source_sequence,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    async with cast(asyncpg.Pool, pool).acquire() as raw_connection:
        repository = PostgresFrontendWorkflowEventRepository(
            cast(asyncpg.Connection, raw_connection)
        )
        events = await repository.list_frontend_events(
            workflow_run_id,
            cursor,
            limit,
        )

    visible_events = tuple(
        event
        for event in events
        if event.project_id == project_id
        and event.document_id == document_id
        and event.workflow_run_id == workflow_run_id
    )
    next_cursor = _next_frontend_workflow_event_cursor(visible_events)
    return {
        "workflow_run_id": workflow_run_id,
        "after_source_sequence": cursor.source_sequence_number,
        "after_cursor": None if cursor.sequence_only else cursor.serialize(),
        "next_cursor": next_cursor,
        "events": [
            _frontend_workflow_event_read_model(event) for event in visible_events
        ],
    }


def _frontend_workflow_event_read_model(
    event: FrontendWorkflowEvent,
) -> dict[str, object]:
    return {
        "projection_event_id": event.projection_event_id,
        "source_event_id": event.source_event_id,
        "source_sequence_number": event.source_sequence_number,
        "projection_version": event.projection_version,
        "projection_type": event.projection_type,
        "event_type": event.event_type,
        "operation_key": event.operation_key,
        "canonical_phase": event.canonical_phase,
        "workflow_run_id": event.workflow_run_id,
        "project_id": event.project_id,
        "document_id": event.document_id,
        "payload": dict(event.payload),
        "occurred_at": event.occurred_at.isoformat(),
        "causation_command_id": event.causation_command_id,
        "correlation_id": event.correlation_id,
    }


def _frontend_workflow_event_sse(event: FrontendWorkflowEvent) -> str:
    payload = _frontend_workflow_event_read_model(event)
    return (
        f"id: {event.projection_event_id}\n"
        "event: frontend_workflow_event\n"
        f"data: {json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}\n\n"
    )


def _resolve_frontend_workflow_event_cursor(
    *,
    after_cursor: str | None,
    after_source_sequence: int,
) -> FrontendWorkflowEventCursor:
    if isinstance(after_cursor, str) and after_cursor.strip():
        return FrontendWorkflowEventCursor.parse(after_cursor)
    return FrontendWorkflowEventCursor.from_legacy_source_sequence(
        after_source_sequence
    )


def _next_frontend_workflow_event_cursor(
    events: tuple[FrontendWorkflowEvent, ...],
) -> str | None:
    if not events:
        return None
    return FrontendWorkflowEventCursor.from_event(events[-1]).serialize()


@router.get(
    "/source-documents/{document_id}/workflows/{workflow_run_id}/frontend-events/stream"
)
async def stream_knowledge_frontend_workflow_events(
    project_id: str,
    document_id: str,
    workflow_run_id: str,
    request: Request,
    after_cursor: str | None = Query(default=None),
    after_source_sequence: int = Query(0, ge=0),
    authorization: str | None = Header(default=None),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
) -> StreamingResponse:
    """Streams persisted frontend projection events with bounded polling."""

    await _require_project_access(
        project_id=project_id,
        authorization=authorization,
        project_repo=project_repo,
        user_repo=user_repo,
    )

    try:
        cursor = _resolve_frontend_workflow_event_cursor(
            after_cursor=after_cursor,
            after_source_sequence=after_source_sequence,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    async def event_stream():
        replay_cursor = cursor
        async with cast(asyncpg.Pool, pool).acquire() as raw_connection:
            repository = PostgresFrontendWorkflowEventRepository(
                cast(asyncpg.Connection, raw_connection)
            )
            replay_events = await repository.list_frontend_events(
                workflow_run_id,
                replay_cursor,
                200,
            )

        for event in replay_events:
            replay_cursor = FrontendWorkflowEventCursor.from_event(event)
            if (
                event.project_id == project_id
                and event.document_id == document_id
                and event.workflow_run_id == workflow_run_id
            ):
                yield _frontend_workflow_event_sse(event)

        if await request.is_disconnected():
            return

        try:
            async with subscribe_frontend_workflow_events(
                workflow_run_id=workflow_run_id,
            ) as subscription:
                while True:
                    if await request.is_disconnected():
                        return

                    event = await subscription.next_event(timeout_seconds=15.0)
                    if event is None:
                        yield ": keepalive\n\n"
                        continue

                    if (
                        event.project_id == project_id
                        and event.document_id == document_id
                        and event.workflow_run_id == workflow_run_id
                        and event.source_sequence_number
                        > replay_cursor.source_sequence_number
                    ):
                        replay_cursor = FrontendWorkflowEventCursor.from_event(event)
                        yield _frontend_workflow_event_sse(event)
        except Exception as exc:
            logger.warning(
                "Frontend workflow event Redis stream unavailable",
                extra={"error": str(exc)},
            )
            return

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/source-documents/{source_document_ref}/draft-claims")
async def source_document_draft_claims(
    project_id: str,
    source_document_ref: str,
    authorization: str | None = Header(default=None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
):
    """Returns draft claim observations extracted for a source document."""

    await _require_project_access(
        project_id=project_id,
        authorization=authorization,
        project_repo=project_repo,
        user_repo=user_repo,
    )

    repository = PostgresDraftClaimObservationReadRepository(pool)
    items = await repository.list_by_source_document_ref(
        source_document_ref=source_document_ref,
        limit=limit,
        offset=offset,
    )

    return {
        "source_document_ref": source_document_ref,
        "count": len(items),
        "limit": limit,
        "offset": offset,
        "items": [_draft_claim_observation_read_model(item) for item in items],
    }


@router.get("/source-units/{source_unit_ref}/draft-claims")
async def source_unit_draft_claims(
    project_id: str,
    source_unit_ref: str,
    authorization: str | None = Header(default=None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
):
    """Returns draft claim observations extracted for one source unit."""

    await _require_project_access(
        project_id=project_id,
        authorization=authorization,
        project_repo=project_repo,
        user_repo=user_repo,
    )

    repository = PostgresDraftClaimObservationReadRepository(pool)
    items = await repository.list_by_source_unit_ref(
        source_unit_ref=source_unit_ref,
        limit=limit,
        offset=offset,
    )

    return {
        "source_unit_ref": source_unit_ref,
        "count": len(items),
        "limit": limit,
        "offset": offset,
        "items": [_draft_claim_observation_read_model(item) for item in items],
    }


@router.get("/workflows/{workflow_run_id}/draft-claim-compaction-frontier")
async def workflow_draft_claim_compaction_frontier(
    project_id: str,
    workflow_run_id: str,
    authorization: str | None = Header(default=None),
    group_ref: str | None = Query(default=None),
    include_inactive: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
):
    await _require_project_access(
        project_id=project_id,
        authorization=authorization,
        project_repo=project_repo,
        user_repo=user_repo,
    )

    normalized_workflow_run_id = _normalize_optional_query_text(workflow_run_id)
    if normalized_workflow_run_id is None:
        raise HTTPException(status_code=400, detail="workflow_run_id must be non-empty")
    normalized_group_ref = _normalize_optional_query_text(group_ref)

    repository = PostgresDraftClaimCompactionReductionStateRepository(pool)
    try:
        frontier = await repository.list_compaction_frontier_for_workflow(
            workflow_run_id=normalized_workflow_run_id,
            group_ref=normalized_group_ref,
            include_inactive=include_inactive,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _draft_claim_compaction_frontier_read_model(
        frontier,
        limit=limit,
        offset=offset,
        include_inactive=include_inactive,
    )


@router.get("/workflows/{workflow_run_id}/draft-claim-compaction-nodes")
async def workflow_draft_claim_compaction_nodes(
    project_id: str,
    workflow_run_id: str,
    authorization: str | None = Header(default=None),
    group_ref: str | None = Query(default=None),
    node_ref: str | None = Query(default=None),
    active_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
):
    await _require_project_access(
        project_id=project_id,
        authorization=authorization,
        project_repo=project_repo,
        user_repo=user_repo,
    )

    normalized_workflow_run_id = _normalize_optional_query_text(workflow_run_id)
    if normalized_workflow_run_id is None:
        raise HTTPException(status_code=400, detail="workflow_run_id must be non-empty")
    normalized_group_ref = _normalize_optional_query_text(group_ref)
    normalized_node_ref = _normalize_optional_query_text(node_ref)

    repository = PostgresDraftClaimCompactionReductionStateRepository(pool)
    try:
        items = await repository.list_compaction_nodes_for_workflow(
            workflow_run_id=normalized_workflow_run_id,
            group_ref=normalized_group_ref,
            node_ref=normalized_node_ref,
            active_only=active_only,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "workflow_run_id": normalized_workflow_run_id,
        "group_ref": normalized_group_ref,
        "node_ref": normalized_node_ref,
        "active_only": active_only,
        "count": len(items),
        "limit": limit,
        "offset": offset,
        "items": [_draft_claim_compaction_node_read_model(item) for item in items],
    }


@router.get("/workflows/{workflow_run_id}/draft-claims")
async def workflow_draft_claims(
    project_id: str,
    workflow_run_id: str,
    authorization: str | None = Header(default=None),
    source_unit_ref: str | None = Query(default=None),
    work_item_id: str | None = Query(default=None),
    dispatch_attempt_id: str | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
):
    """Returns draft claim observations for a workflow execution scope."""

    await _require_project_access(
        project_id=project_id,
        authorization=authorization,
        project_repo=project_repo,
        user_repo=user_repo,
    )

    normalized_workflow_run_id = _normalize_optional_query_text(workflow_run_id)
    if normalized_workflow_run_id is None:
        raise HTTPException(status_code=400, detail="workflow_run_id must be non-empty")

    normalized_source_unit_ref = _normalize_optional_query_text(source_unit_ref)
    normalized_work_item_id = _normalize_optional_query_text(work_item_id)
    normalized_dispatch_attempt_id = _normalize_optional_query_text(dispatch_attempt_id)
    _require_workflow_draft_claim_scope_filter(
        source_unit_ref=normalized_source_unit_ref,
        work_item_id=normalized_work_item_id,
        dispatch_attempt_id=normalized_dispatch_attempt_id,
    )

    repository = PostgresDraftClaimObservationReadRepository(pool)
    try:
        items = await repository.list_by_workflow_scope(
            workflow_run_id=normalized_workflow_run_id,
            source_unit_ref=normalized_source_unit_ref,
            work_item_id=normalized_work_item_id,
            dispatch_attempt_id=normalized_dispatch_attempt_id,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "workflow_run_id": normalized_workflow_run_id,
        "source_unit_ref": normalized_source_unit_ref,
        "work_item_id": normalized_work_item_id,
        "dispatch_attempt_id": normalized_dispatch_attempt_id,
        "count": len(items),
        "limit": limit,
        "offset": offset,
        "items": [_draft_claim_observation_read_model(item) for item in items],
    }


@router.get("/workflows/{workflow_run_id}/draft-claim-clusters")
async def workflow_draft_claim_clusters(
    project_id: str,
    workflow_run_id: str,
    authorization: str | None = Header(default=None),
    include_batches: bool = Query(True),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
):
    """Returns DraftClaimClusterGroup rows for one workflow."""

    await _require_project_access(
        project_id=project_id,
        authorization=authorization,
        project_repo=project_repo,
        user_repo=user_repo,
    )

    normalized_workflow_run_id = _normalize_optional_query_text(workflow_run_id)
    if normalized_workflow_run_id is None:
        raise HTTPException(status_code=400, detail="workflow_run_id must be non-empty")

    repository = PostgresDraftClaimCompactionPlanRepository(pool)
    groups = await repository.list_cluster_groups_for_workflow(
        workflow_run_id=normalized_workflow_run_id,
        limit=limit,
        offset=offset,
    )
    batches_by_group: dict[str, list[DraftClaimCompactionBatchReadModel]] = {}
    if include_batches and groups:
        group_refs = {group.group_ref for group in groups}
        for batch in await repository.list_cluster_batches_for_workflow(
            workflow_run_id=normalized_workflow_run_id,
        ):
            if batch.group_ref in group_refs:
                batches_by_group.setdefault(batch.group_ref, []).append(batch)

    return {
        "workflow_run_id": normalized_workflow_run_id,
        "count": len(groups),
        "limit": limit,
        "offset": offset,
        "include_batches": include_batches,
        "groups": [
            _draft_claim_cluster_group_read_model(
                group,
                batches=tuple(batches_by_group.get(group.group_ref, ())),
            )
            for group in groups
        ],
    }


@router.get("/workflows/{workflow_run_id}/draft-claim-clusters/{group_ref}/members")
async def workflow_draft_claim_cluster_members(
    project_id: str,
    workflow_run_id: str,
    group_ref: str,
    authorization: str | None = Header(default=None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
):
    """Returns member refs for an expanded DraftClaimClusterGroup row."""

    await _require_project_access(
        project_id=project_id,
        authorization=authorization,
        project_repo=project_repo,
        user_repo=user_repo,
    )

    normalized_workflow_run_id = _normalize_optional_query_text(workflow_run_id)
    normalized_group_ref = _normalize_optional_query_text(group_ref)
    if normalized_workflow_run_id is None:
        raise HTTPException(status_code=400, detail="workflow_run_id must be non-empty")
    if normalized_group_ref is None:
        raise HTTPException(status_code=400, detail="group_ref must be non-empty")

    repository = PostgresDraftClaimCompactionPlanRepository(pool)
    members = await repository.list_cluster_members_for_group(
        workflow_run_id=normalized_workflow_run_id,
        group_ref=normalized_group_ref,
        limit=limit,
        offset=offset,
    )

    return {
        "workflow_run_id": normalized_workflow_run_id,
        "group_ref": normalized_group_ref,
        "count": len(members),
        "limit": limit,
        "offset": offset,
        "items": [_draft_claim_cluster_member_read_model(member) for member in members],
    }


@router.post("/workflows/{workflow_run_id}/curation-workspace/open")
async def open_draft_claim_curation_workspace(
    project_id: str,
    workflow_run_id: str,
    authorization: str | None = Header(default=None),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
):
    await _require_project_access(
        project_id=project_id,
        authorization=authorization,
        project_repo=project_repo,
        user_repo=user_repo,
    )
    (
        curation_repository,
        compaction_repository,
        draft_claim_repository,
        source_repository,
        saga_state_repository,
    ) = _curation_workspace_repositories(pool)
    workflow_project = await _ensure_curation_workflow_project(
        workflow_run_id=workflow_run_id,
        project_id=project_id,
        saga_state_repository=saga_state_repository,
    )
    try:
        await OpenDraftClaimCurationWorkspace(
            curation_workspace_repository=curation_repository,
            compaction_reduction_state_repository=compaction_repository,
        ).execute(
            workflow_run_id=workflow_run_id,
            project_id=workflow_project.project_id,
            source_document_ref=workflow_project.source_document_ref,
            created_at=datetime.now(timezone.utc),
        )
    except DraftClaimCurationWorkspaceProjectMismatchError as exc:
        raise HTTPException(status_code=404, detail="Workflow not found") from exc
    except DraftClaimCurationWorkspaceOpenError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return await _read_curation_workspace_response(
        workflow_run_id=workflow_run_id,
        curation_repository=curation_repository,
        compaction_repository=compaction_repository,
        draft_claim_repository=draft_claim_repository,
        source_repository=source_repository,
    )


@router.get("/workflows/{workflow_run_id}/curation-workspace")
async def read_draft_claim_curation_workspace(
    project_id: str,
    workflow_run_id: str,
    authorization: str | None = Header(default=None),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
):
    await _require_project_access(
        project_id=project_id,
        authorization=authorization,
        project_repo=project_repo,
        user_repo=user_repo,
    )
    (
        curation_repository,
        compaction_repository,
        draft_claim_repository,
        source_repository,
        saga_state_repository,
    ) = _curation_workspace_repositories(pool)
    await _ensure_curation_workflow_project(
        workflow_run_id=workflow_run_id,
        project_id=project_id,
        saga_state_repository=saga_state_repository,
    )
    return await _read_curation_workspace_response(
        workflow_run_id=workflow_run_id,
        curation_repository=curation_repository,
        compaction_repository=compaction_repository,
        draft_claim_repository=draft_claim_repository,
        source_repository=source_repository,
    )


@router.patch("/workflows/{workflow_run_id}/curation-workspace/items/{item_ref}")
async def update_draft_claim_curation_item(
    project_id: str,
    workflow_run_id: str,
    item_ref: str,
    updates: dict[str, object] = Body(...),
    authorization: str | None = Header(default=None),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
):
    await _require_project_access(
        project_id=project_id,
        authorization=authorization,
        project_repo=project_repo,
        user_repo=user_repo,
    )
    (
        curation_repository,
        _compaction_repository,
        _draft_claim_repository,
        _source_repository,
        saga_state_repository,
    ) = _curation_workspace_repositories(pool)
    await _ensure_curation_workflow_project(
        workflow_run_id=workflow_run_id,
        project_id=project_id,
        saga_state_repository=saga_state_repository,
    )
    try:
        item = await UpdateDraftClaimCurationItem(
            curation_workspace_repository=curation_repository,
        ).execute(
            workflow_run_id=workflow_run_id,
            item_ref=item_ref,
            updates=updates,
            updated_at=datetime.now(timezone.utc),
        )
    except DraftClaimCurationItemUpdateError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"item": item.to_json_dict()}


@router.post("/workflows/{workflow_run_id}/curation-workspace/items/{item_ref}/exclude")
async def exclude_draft_claim_curation_item(
    project_id: str,
    workflow_run_id: str,
    item_ref: str,
    payload: dict[str, object] | None = Body(default=None),
    authorization: str | None = Header(default=None),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
):
    await _require_project_access(
        project_id=project_id,
        authorization=authorization,
        project_repo=project_repo,
        user_repo=user_repo,
    )
    body = payload or {}
    reason = body.get("exclusion_reason")
    if reason is not None and not isinstance(reason, str):
        raise HTTPException(status_code=400, detail="exclusion_reason must be str")
    (
        curation_repository,
        _compaction_repository,
        _draft_claim_repository,
        _source_repository,
        saga_state_repository,
    ) = _curation_workspace_repositories(pool)
    await _ensure_curation_workflow_project(
        workflow_run_id=workflow_run_id,
        project_id=project_id,
        saga_state_repository=saga_state_repository,
    )
    try:
        item = await SetDraftClaimCurationItemExcluded(
            curation_workspace_repository=curation_repository,
        ).execute(
            workflow_run_id=workflow_run_id,
            item_ref=item_ref,
            excluded=True,
            exclusion_reason=reason,
            updated_at=datetime.now(timezone.utc),
        )
    except DraftClaimCurationItemExclusionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"item": item.to_json_dict()}


@router.post("/workflows/{workflow_run_id}/curation-workspace/items/{item_ref}/include")
async def include_draft_claim_curation_item(
    project_id: str,
    workflow_run_id: str,
    item_ref: str,
    authorization: str | None = Header(default=None),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
):
    await _require_project_access(
        project_id=project_id,
        authorization=authorization,
        project_repo=project_repo,
        user_repo=user_repo,
    )
    (
        curation_repository,
        _compaction_repository,
        _draft_claim_repository,
        _source_repository,
        saga_state_repository,
    ) = _curation_workspace_repositories(pool)
    await _ensure_curation_workflow_project(
        workflow_run_id=workflow_run_id,
        project_id=project_id,
        saga_state_repository=saga_state_repository,
    )
    try:
        item = await SetDraftClaimCurationItemExcluded(
            curation_workspace_repository=curation_repository,
        ).execute(
            workflow_run_id=workflow_run_id,
            item_ref=item_ref,
            excluded=False,
            exclusion_reason=None,
            updated_at=datetime.now(timezone.utc),
        )
    except DraftClaimCurationItemExclusionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"item": item.to_json_dict()}


@router.post("/workflows/{workflow_run_id}/curation-workspace/publish")
async def publish_draft_claim_curation_workspace(
    project_id: str,
    workflow_run_id: str,
    authorization: str | None = Header(default=None),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
):
    await _require_project_access(
        project_id=project_id,
        authorization=authorization,
        project_repo=project_repo,
        user_repo=user_repo,
    )
    (
        curation_repository,
        _compaction_repository,
        _draft_claim_repository,
        _source_repository,
        saga_state_repository,
    ) = _curation_workspace_repositories(pool)
    await _ensure_curation_workflow_project(
        workflow_run_id=workflow_run_id,
        project_id=project_id,
        saga_state_repository=saga_state_repository,
    )

    from src.contexts.embedding_runtime.infrastructure.composition.embedding_generation_provider_factory import (
        make_embedding_generation_port,
    )
    from src.contexts.embedding_runtime.infrastructure.config.embedding_runtime_settings import (
        load_embedding_runtime_settings,
    )
    from src.contexts.knowledge_workbench.curation.infrastructure.postgres.postgres_draft_claim_curation_publication_repository import (
        PostgresDraftClaimCurationPublicationRepository,
    )

    try:
        await _enqueue_draft_claim_curation_publication(
            pool=cast(AsyncPool, pool),
            workflow_run_id=workflow_run_id,
            requested_at=datetime.now(timezone.utc),
        )
        drain_result = await make_knowledge_extraction_workflow_resume(
            pool=cast(AsyncPool, pool),
        ).execute(
            RunKnowledgeExtractionWorkflowResumeCommand(
                project_id=project_id,
                document_id=workflow_run_id,
                max_drain_commands=10,
            )
        )
        if drain_result.blocked_command_type is not None:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Curation publication remains pending: "
                    f"{drain_result.blocked_reason}"
                ),
            )

        embedding_settings = load_embedding_runtime_settings()
        result = await PublishDraftClaimCurationWorkspace(
            curation_workspace_repository=curation_repository,
            curation_publication_repository=PostgresDraftClaimCurationPublicationRepository(
                pool
            ),
            embedding_generation_port=make_embedding_generation_port(
                embedding_settings
            ),
            embedding_model_id=embedding_settings.local_model,
            embedding_dimensions=embedding_settings.vector_dimensions,
        ).execute(
            workflow_run_id=workflow_run_id,
            published_at=datetime.now(timezone.utc),
        )
    except DraftClaimCurationPublicationNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail="Curation workspace not found"
        ) from exc
    except (
        DraftClaimCurationPublicationAlreadyPublishedError,
        DraftClaimCurationPublicationEmptyError,
    ) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except DraftClaimCurationPublicationEmbeddingError as exc:
        raise HTTPException(
            status_code=502,
            detail="Failed to generate publication embeddings",
        ) from exc

    return result.to_json_dict()


async def _enqueue_draft_claim_curation_publication(
    *,
    pool: AsyncPool,
    workflow_run_id: str,
    requested_at: datetime,
) -> None:
    connection = await pool.acquire()
    workflow_unit_of_work = PostgresWorkflowRuntimeUnitOfWork(
        cast(asyncpg.Connection, connection)
    )
    await workflow_unit_of_work.start()
    idempotency_key = f"draft-claim-curation-publish:{workflow_run_id}"
    try:
        await workflow_unit_of_work.command_log.append_pending_command(
            WorkflowCommand(
                command_id=WorkflowCommandId(f"workflow-command:{idempotency_key}"),
                command_type=(
                    KnowledgeExtractionCanonicalCommandType.PUBLISH_DRAFT_CLAIM_CURATION_WORKSPACE.value
                ),
                workflow_run_id=workflow_run_id,
                idempotency_key=WorkflowIdempotencyKey(idempotency_key),
                payload={"workflow_run_id": workflow_run_id},
                status=WorkflowCommandStatus.PENDING,
                run_after=requested_at,
                created_at=requested_at,
                updated_at=requested_at,
            )
        )
        await workflow_unit_of_work.commit()
    except Exception:
        await workflow_unit_of_work.rollback()
        raise
    finally:
        await pool.release(connection)


@router.post("/rag-eval/workbench/run")
async def run_workbench_rag_eval(
    project_id: str,
    payload: dict[str, object] = Body(default_factory=dict),
    authorization: str | None = Header(default=None),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
    llm_executor: LlmDispatchExecutorPort = Depends(get_llm_dispatch_executor),
):
    await _require_project_access(
        project_id=project_id,
        authorization=authorization,
        project_repo=project_repo,
        user_repo=user_repo,
    )

    publication_id = _optional_payload_str(payload, "publication_id")
    source_document_ref = _optional_payload_str(payload, "source_document_ref")
    top_k = _optional_payload_int(payload, "top_k")
    if top_k is not None and top_k < 5:
        raise HTTPException(status_code=400, detail="top_k must be at least 5")
    max_entries = _payload_int(payload, "max_entries", default=20)
    allow_degraded_llama_instant = _payload_bool(
        payload,
        "allow_degraded_llama_instant",
        default=False,
    )
    if max_entries < 1 or max_entries > 50:
        raise HTTPException(
            status_code=400, detail="max_entries must be between 1 and 50"
        )

    try:
        from src.interfaces.composition.workbench_rag_eval import (
            make_run_workbench_rag_eval,
        )

        summary = await make_run_workbench_rag_eval(
            pool=pool,
            llm_dispatch_executor=llm_executor,
        ).execute(
            project_id=project_id,
            publication_id=publication_id,
            source_document_ref=source_document_ref,
            top_k=top_k,
            max_entries=max_entries,
            now=datetime.now(timezone.utc),
            allow_degraded_llama_instant=allow_degraded_llama_instant,
        )
    except WorkbenchRagEvalDegradedFallbackRequiredError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "status": "requires_degraded_fallback_confirmation",
                "message": str(exc),
                "degraded_model": "llama-3.1-8b-instant",
            },
        ) from exc
    except WorkbenchRagEvalQuestionGenerationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"run": summary.to_json_dict()}


@router.get("/rag-eval/workbench/latest")
async def latest_workbench_rag_eval(
    project_id: str,
    authorization: str | None = Header(default=None),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
):
    await _require_project_access(
        project_id=project_id,
        authorization=authorization,
        project_repo=project_repo,
        user_repo=user_repo,
    )
    summary = await PostgresWorkbenchRagEvalRepository(pool).get_latest_run(
        project_id=project_id
    )
    return {"run": summary.to_json_dict() if summary is not None else None}


@router.get("/rag-eval/workbench/runs/{run_id}")
async def get_workbench_rag_eval_run(
    project_id: str,
    run_id: str,
    authorization: str | None = Header(default=None),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
):
    await _require_project_access(
        project_id=project_id,
        authorization=authorization,
        project_repo=project_repo,
        user_repo=user_repo,
    )
    summary = await PostgresWorkbenchRagEvalRepository(pool).get_run(
        run_id=run_id,
        project_id=project_id,
    )
    if summary is None:
        raise HTTPException(status_code=404, detail="Workbench RAG Eval run not found")
    return {"run": summary.to_json_dict()}


@router.post("/rag-eval/workbench/promotion-candidates/apply-batch")
async def apply_workbench_rag_eval_promotion_candidates_batch(
    project_id: str,
    payload: Mapping[str, object],
    authorization: str | None = Header(default=None),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
):
    await _require_project_access(
        project_id=project_id,
        authorization=authorization,
        project_repo=project_repo,
        user_repo=user_repo,
    )

    mode = _payload_text(payload, "mode")
    promotion_ids = _payload_text_tuple(payload, "promotion_ids", default=())
    run_id = _optional_payload_text(payload, "run_id")

    try:
        from src.interfaces.composition.workbench_rag_eval import (
            make_apply_workbench_rag_eval_promotions_batch,
        )

        result = await make_apply_workbench_rag_eval_promotions_batch(
            pool=pool
        ).execute(
            project_id=project_id,
            mode=mode,
            promotion_ids=promotion_ids,
            run_id=run_id,
            applied_at=datetime.now(timezone.utc),
        )
    except WorkbenchRagEvalPromotionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except WorkbenchRagEvalPromotionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except WorkbenchRagEvalPromotionEmbeddingError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"result": result.to_json_dict()}


@router.post("/rag-eval/workbench/promotion-candidates/{promotion_id}/apply")
async def apply_workbench_rag_eval_promotion_candidate(
    project_id: str,
    promotion_id: str,
    authorization: str | None = Header(default=None),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
):
    await _require_project_access(
        project_id=project_id,
        authorization=authorization,
        project_repo=project_repo,
        user_repo=user_repo,
    )

    try:
        from src.interfaces.composition.workbench_rag_eval import (
            make_apply_workbench_rag_eval_promotion,
        )

        result = await make_apply_workbench_rag_eval_promotion(pool=pool).execute(
            project_id=project_id,
            promotion_id=promotion_id,
            applied_at=datetime.now(timezone.utc),
        )
    except WorkbenchRagEvalPromotionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except WorkbenchRagEvalPromotionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except WorkbenchRagEvalPromotionEmbeddingError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"result": result.to_json_dict()}


@router.get("/rag-eval/workbench/runs/{run_id}/questions")
async def list_workbench_rag_eval_questions(
    project_id: str,
    run_id: str,
    authorization: str | None = Header(default=None),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
):
    await _require_project_access(
        project_id=project_id,
        authorization=authorization,
        project_repo=project_repo,
        user_repo=user_repo,
    )
    repository = PostgresWorkbenchRagEvalRepository(pool)
    summary = await repository.get_run(run_id=run_id, project_id=project_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Workbench RAG Eval run not found")
    questions = await repository.list_run_questions(
        project_id=project_id,
        run_id=run_id,
    )
    return {"questions": [question.to_json_dict() for question in questions]}


@router.get("/rag-eval/workbench/runs/{run_id}/promotion-candidates")
async def list_workbench_rag_eval_promotion_candidates(
    project_id: str,
    run_id: str,
    authorization: str | None = Header(default=None),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
):
    await _require_project_access(
        project_id=project_id,
        authorization=authorization,
        project_repo=project_repo,
        user_repo=user_repo,
    )
    repository = PostgresWorkbenchRagEvalRepository(pool)
    summary = await repository.get_run(run_id=run_id, project_id=project_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="Workbench RAG Eval run not found")
    candidates = await repository.list_run_promotion_candidates(
        project_id=project_id,
        run_id=run_id,
    )
    return {"candidates": [candidate.to_json_dict() for candidate in candidates]}


@router.get("/{document_id}/workflow-live-state")
async def knowledge_workflow_live_state(
    project_id: str,
    document_id: str,
    authorization: str | None = Header(default=None),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
):
    """Returns bootstrap/recovery/debug Workbench workflow snapshot for one document.

    This endpoint is intentionally read-only. Workflow liveness is owned by
    upload/resume/lifespan/worker/admin command paths, never by frontend reads.
    """

    await _require_project_access(
        project_id=project_id,
        authorization=authorization,
        project_repo=project_repo,
        user_repo=user_repo,
    )

    try:
        return await fetch_workbench_workflow_live_state(
            pool=pool,
            project_id=project_id,
            document_id=document_id,
        )
    except WorkbenchWorkflowLiveStateNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail="Knowledge document not found",
        ) from exc


@router.get("/{document_id}/progress")
async def knowledge_processing_progress(
    project_id: str,
    document_id: str,
    authorization: str | None = Header(default=None),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
):
    """Returns source-ingestion/Workbench processing progress for one document."""

    await _require_project_access(
        project_id=project_id,
        authorization=authorization,
        project_repo=project_repo,
        user_repo=user_repo,
    )

    document_ref = SourceDocumentRef(document_id)
    source_repository = PostgresSourceManagementRepository(pool)
    source_document = await source_repository.load_source_document(document_ref)
    if source_document is None:
        raise HTTPException(status_code=404, detail="Knowledge document not found")

    source_units = await source_repository.list_source_units_for_document(document_ref)
    source_unit_count = len(source_units)

    workflow_run_id = f"knowledge-extraction:{document_id}"
    workflow_state_repository = PostgresKnowledgeExtractionSagaStateRepository(pool)
    workflow_state = await workflow_state_repository.load_workflow_state(
        workflow_run_id
    )

    workflow_status = (
        workflow_state.status.value if workflow_state is not None else "running"
    )
    current_phase = (
        workflow_state.current_phase.value
        if workflow_state is not None
        else "source_units_created"
    )
    checkpoints = workflow_state.checkpoints if workflow_state is not None else ()

    expected_count = sum(checkpoint.expected_count for checkpoint in checkpoints)
    completed_count = sum(checkpoint.completed_count for checkpoint in checkpoints)
    failed_count = sum(checkpoint.failed_count for checkpoint in checkpoints)
    blocked_count = sum(checkpoint.blocked_count for checkpoint in checkpoints)

    progress_percent = 0
    if expected_count > 0:
        progress_percent = max(
            0,
            min(100, round((completed_count / expected_count) * 100)),
        )
    elif source_unit_count > 0:
        progress_percent = 10

    metrics = {
        "source_unit_count": source_unit_count,
        "raw_source_unit_count": source_unit_count,
        "workflow_checkpoint_expected_count": expected_count,
        "workflow_checkpoint_completed_count": completed_count,
        "workflow_checkpoint_failed_count": failed_count,
        "workflow_checkpoint_blocked_count": blocked_count,
    }

    updated_at = (
        workflow_state.updated_at
        if workflow_state is not None and workflow_state.updated_at is not None
        else source_document.created_at
    )

    return {
        "document_id": document_id,
        "project_id": project_id,
        "status": workflow_status,
        "current_phase": current_phase,
        "progress_percent": progress_percent,
        "metrics": metrics,
        "actions": [],
        "issue": None,
        "updated_at": updated_at.isoformat(),
    }


@router.post("/preview")
async def preview_knowledge():
    _legacy_endpoint_gone(
        capability="retrieval preview",
        target="WorkbenchRetrievalPreviewService or RuntimeRetrievalPreviewService",
    )


@router.get("/usage")
async def knowledge_usage(
    project_id: str,
    authorization: str | None = Header(default=None),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
):
    await _require_project_access(
        project_id=project_id,
        authorization=authorization,
        project_repo=project_repo,
        user_repo=user_repo,
    )

    from src.application.dto.model_usage_dto import ModelUsageSummaryDto
    from src.infrastructure.db.repositories.model_usage_repository import (
        ModelUsageRepository,
    )

    repository = ModelUsageRepository(pool)
    monthly_budget_tokens = int(
        getattr(
            settings,
            "MODEL_USAGE_MONTHLY_TOKEN_BUDGET",
            getattr(settings, "model_usage_monthly_token_budget", 0),
        )
        or 0
    )

    now_utc = datetime.now(timezone.utc)
    today_start_utc = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start_utc = today_start_utc.replace(day=1)
    if month_start_utc.month == 12:
        month_end_utc = month_start_utc.replace(
            year=month_start_utc.year + 1,
            month=1,
        )
    else:
        month_end_utc = month_start_utc.replace(month=month_start_utc.month + 1)

    summary = await repository.get_project_usage_summary(
        project_id=project_id,
        month_start_utc=month_start_utc,
        month_end_utc=month_end_utc,
        today_start_utc=today_start_utc,
        monthly_budget_tokens=monthly_budget_tokens,
    )

    if hasattr(summary, "to_dict"):
        return summary.to_dict()

    return ModelUsageSummaryDto.from_view(
        summary,
        counter_enabled=True,
    ).to_dict()


@router.get("/{document_id}/source-units")
async def knowledge_source_units(
    project_id: str,
    document_id: str,
    authorization: str | None = Header(default=None),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
):
    """Returns source-ingestion source units for one document."""

    await _require_project_access(
        project_id=project_id,
        authorization=authorization,
        project_repo=project_repo,
        user_repo=user_repo,
    )

    document_ref = SourceDocumentRef(document_id)
    repository = PostgresSourceManagementRepository(pool)
    source_document = await repository.load_source_document(document_ref)
    if source_document is None:
        raise HTTPException(status_code=404, detail="Knowledge document not found")

    source_units = await repository.list_source_units_for_document(document_ref)

    return {
        "document_id": document_id,
        "source_units": [
            {
                "id": unit.unit_ref.value,
                "source_index": unit.ordinal,
                "title": " / ".join(unit.heading_path.parts) or unit.unit_ref.value,
                "content": unit.text.value,
                "page": None,
                "start_offset": None,
                "end_offset": None,
                "metadata": {
                    "document_ref": unit.document_ref.value,
                    "unit_kind": unit.unit_kind.value,
                    "heading_path": list(unit.heading_path.parts),
                    "lineage": {
                        "parent_refs": [
                            parent_ref.value for parent_ref in unit.lineage.parent_refs
                        ],
                    },
                    "source_format": source_document.source_format.value,
                },
                "draft_count": 0,
                "draft_titles": [],
                "draft_ids": [],
            }
            for unit in source_units
        ],
        "total_count": len(source_units),
    }


@router.get("/{document_id}/import-quality")
async def knowledge_import_quality_report(
    project_id: str,
    document_id: str,
    authorization: str | None = Header(default=None),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
):
    """Returns source-ingestion import quality for one Workbench document."""

    await _require_project_access(
        project_id=project_id,
        authorization=authorization,
        project_repo=project_repo,
        user_repo=user_repo,
    )

    document_ref = SourceDocumentRef(document_id)
    repository = PostgresSourceManagementRepository(pool)
    source_document = await repository.load_source_document(document_ref)
    if source_document is None:
        raise HTTPException(status_code=404, detail="Knowledge document not found")

    source_units = await repository.list_source_units_for_document(document_ref)
    source_units_count = len(source_units)
    empty_units_count = sum(1 for unit in source_units if not unit.text.value.strip())
    short_units_count = sum(
        1 for unit in source_units if 0 < len(unit.text.value.strip()) < 120
    )
    table_like_units_count = sum(
        1 for unit in source_units if "|" in unit.text.value or "\t" in unit.text.value
    )
    heading_counts: dict[str, int] = {}
    for unit in source_units:
        heading_key = " / ".join(unit.heading_path.parts)
        if heading_key:
            heading_counts[heading_key] = heading_counts.get(heading_key, 0) + 1
    duplicated_headings_count = sum(1 for count in heading_counts.values() if count > 1)

    warnings: list[dict[str, str]] = []
    if source_units_count == 0:
        warnings.append(
            {
                "code": "no_source_units",
                "severity": "warning",
                "message": "Source ingestion has not produced source units yet.",
            }
        )
    if empty_units_count > 0:
        warnings.append(
            {
                "code": "empty_source_units",
                "severity": "warning",
                "message": "Some source units are empty.",
            }
        )

    safe_to_compile = source_units_count > 0 and empty_units_count < source_units_count
    status = "good" if safe_to_compile and not warnings else "needs_review"

    return {
        "document_id": document_id,
        "status": status,
        "safe_to_compile": safe_to_compile,
        "source_format": source_document.source_format.value,
        "extracted_text_chars": sum(len(unit.text.value) for unit in source_units),
        "source_units_count": source_units_count,
        "empty_units_count": empty_units_count,
        "short_units_count": short_units_count,
        "table_like_units_count": table_like_units_count,
        "duplicated_headings_count": duplicated_headings_count,
        "source_refs_ready": source_units_count > 0,
        "warnings": warnings,
        "recommended_action": (
            "continue_processing" if safe_to_compile else "wait_for_source_units"
        ),
    }


@router.get("/{document_id}/price-facts")
async def knowledge_price_facts(
    project_id: str,
    document_id: str,
    authorization: str | None = Header(default=None),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
):
    await _require_project_access(
        project_id=project_id,
        authorization=authorization,
        project_repo=project_repo,
        user_repo=user_repo,
    )
    from src.interfaces.composition.commercial_price_review import (
        make_commercial_price_review_service,
    )

    service = make_commercial_price_review_service(pool)
    return await service.price_facts(document_id=document_id)


@router.get("/commercial-truth-review")
async def project_commercial_truth_review(
    project_id: str,
    policy: CommercialTruthResolutionPolicy = CommercialTruthResolutionPolicy.MANUAL_REVIEW,
    authorization: str | None = Header(default=None),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
):
    await _require_project_access(
        project_id=project_id,
        authorization=authorization,
        project_repo=project_repo,
        user_repo=user_repo,
    )
    from src.interfaces.composition.commercial_price_review import (
        make_commercial_price_review_service,
    )

    service = make_commercial_price_review_service(pool)
    return await service.project_commercial_truth_review(
        project_id=project_id,
        policy=policy,
    )


@router.get("/{document_id}/commercial-truth-review")
async def knowledge_commercial_truth_review(
    project_id: str,
    document_id: str,
    policy: CommercialTruthResolutionPolicy = CommercialTruthResolutionPolicy.MANUAL_REVIEW,
    authorization: str | None = Header(default=None),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
):
    await _require_project_access(
        project_id=project_id,
        authorization=authorization,
        project_repo=project_repo,
        user_repo=user_repo,
    )
    from src.interfaces.composition.commercial_price_review import (
        make_commercial_price_review_service,
    )

    service = make_commercial_price_review_service(pool)
    return await service.commercial_truth_review(
        document_id=document_id,
        policy=policy,
    )


@router.post("/{document_id}/price-facts/publish")
async def publish_knowledge_price_facts(
    project_id: str,
    document_id: str,
    fact_ids: list[str] | None = Query(default=None),
    authorization: str | None = Header(default=None),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
):
    await _require_project_access(
        project_id=project_id,
        authorization=authorization,
        project_repo=project_repo,
        user_repo=user_repo,
    )
    from src.interfaces.composition.commercial_price_review import (
        make_commercial_price_review_service,
    )

    service = make_commercial_price_review_service(pool)
    try:
        return await service.publish_price_facts(
            document_id=document_id,
            fact_ids=tuple(fact_ids or ()),
            reviewed_by="http_api",
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{document_id}/price-facts/reject")
async def reject_knowledge_price_facts(
    project_id: str,
    document_id: str,
    fact_ids: list[str] | None = Query(default=None),
    reason: str = "",
    authorization: str | None = Header(default=None),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
):
    await _require_project_access(
        project_id=project_id,
        authorization=authorization,
        project_repo=project_repo,
        user_repo=user_repo,
    )
    from src.interfaces.composition.commercial_price_review import (
        make_commercial_price_review_service,
    )

    service = make_commercial_price_review_service(pool)
    try:
        return await service.reject_price_facts(
            document_id=document_id,
            fact_ids=tuple(fact_ids or ()),
            reviewed_by="http_api",
            reason=reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{document_id}/retighten")
async def retighten_knowledge_document(document_id: str):
    _legacy_endpoint_gone(
        capability=f"answer tightening for {document_id}",
        target="Workbench surface curation/refinement command",
    )


@router.post("/{document_id}/publish-ready")
async def publish_knowledge_ready_answers(
    project_id: str,
    document_id: str,
    authorization: str | None = Header(default=None),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
):
    """Publishes Workbench-approved surfaces into the runtime retrieval surface."""

    await _require_project_access(
        project_id=project_id,
        authorization=authorization,
        project_repo=project_repo,
        user_repo=user_repo,
    )
    _legacy_endpoint_gone(
        capability="publish Workbench-ready surfaces",
        target="Knowledge Workbench publication context",
    )


@router.post("/{document_id}/retry-failed-batches")
async def retry_knowledge_failed_batches(document_id: str):
    _legacy_endpoint_gone(
        capability=f"retry failed compiler batches for {document_id}",
        target="Workbench failed node/section retry command",
    )


async def _latest_workflow_run_id_for_source_document(
    *,
    pool,
    project_id: str,
    source_document_ref: str,
) -> str | None:
    async with pool.acquire() as connection:
        row = await connection.fetchrow(
            """
            SELECT workflow_run_id
            FROM knowledge_extraction_workflow_runs
            WHERE project_id = $1
              AND source_document_ref = $2
            ORDER BY updated_at DESC, created_at DESC
            LIMIT 1
            """,
            project_id,
            source_document_ref,
        )

    if row is None:
        return None

    value = dict(row).get("workflow_run_id")
    if not isinstance(value, str) or not value.strip():
        return None
    return value


@router.post("/source-documents/{source_document_ref}/stop")
async def stop_knowledge_source_document_processing(
    project_id: str,
    source_document_ref: str,
    authorization: str | None = Header(default=None),
    reason: str = Body(default="manual_stop"),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
):
    """Pause active Workbench processing for a source document without deleting artifacts."""

    await _require_project_access(
        project_id=project_id,
        authorization=authorization,
        project_repo=project_repo,
        user_repo=user_repo,
    )

    workflow_run_id = await _latest_workflow_run_id_for_source_document(
        pool=pool,
        project_id=project_id,
        source_document_ref=source_document_ref,
    )
    if workflow_run_id is None:
        raise HTTPException(status_code=404, detail="Workflow not found")

    return await pause_knowledge_extraction_workflow(
        project_id=project_id,
        workflow_run_id=workflow_run_id,
        authorization=authorization,
        reason=reason,
        pool=pool,
        project_repo=project_repo,
        user_repo=user_repo,
    )


@router.post("/source-documents/{source_document_ref}/restore")
@router.post("/source-documents/{source_document_ref}/resume")
async def restore_knowledge_source_document_processing(
    project_id: str,
    source_document_ref: str,
    authorization: str | None = Header(default=None),
    max_drain_commands: int = Query(10, ge=1, le=100),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
    llm_executor: LlmDispatchExecutorPort = Depends(get_llm_dispatch_executor),
):
    """Resume paused Workbench processing for a source document."""

    await _require_project_access(
        project_id=project_id,
        authorization=authorization,
        project_repo=project_repo,
        user_repo=user_repo,
    )

    workflow_run_id = await _latest_workflow_run_id_for_source_document(
        pool=pool,
        project_id=project_id,
        source_document_ref=source_document_ref,
    )
    if workflow_run_id is None:
        raise HTTPException(status_code=404, detail="Workflow not found")

    return await resume_knowledge_extraction_workflow(
        project_id=project_id,
        workflow_run_id=workflow_run_id,
        authorization=authorization,
        max_drain_commands=max_drain_commands,
        pool=pool,
        project_repo=project_repo,
        user_repo=user_repo,
        llm_executor=llm_executor,
    )


def _workflow_run_id_from_live_state(payload: Mapping[str, object]) -> str | None:
    workflow = payload.get("workflow")
    if not isinstance(workflow, Mapping):
        return None

    workflow_run_id = workflow.get("workflow_run_id")
    if isinstance(workflow_run_id, str) and workflow_run_id.strip():
        return workflow_run_id

    return None


def _sse_json_event(event_name: str, payload: Mapping[str, object]) -> str:
    return (
        f"event: {event_name}\n"
        f"data: {json.dumps(dict(payload), ensure_ascii=False, default=str)}\n\n"
    )


@router.get("/{document_id}/workflow-live-state/events")
async def stream_knowledge_workflow_live_state_events(
    project_id: str,
    document_id: str,
    request: Request,
    authorization: str | None = Header(default=None),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
):
    """Compatibility-only snapshot SSE endpoint.

    Projection SSE under /frontend-events/stream is the realtime transport.
    This endpoint must not fetch full live-state snapshots, subscribe to
    legacy PostgreSQL live-state notification channels, or drain workflow commands.
    """

    del request, pool

    await _require_project_access(
        project_id=project_id,
        authorization=authorization,
        project_repo=project_repo,
        user_repo=user_repo,
    )

    async def event_stream():
        yield _sse_json_event(
            "workflow_live_state_deprecated",
            {
                "status": "deprecated_snapshot_sse",
                "message": (
                    "Snapshot SSE is compatibility/bootstrap only. "
                    "Use persisted frontend workflow projection events for realtime."
                ),
                "document_id": document_id,
                "project_id": project_id,
                "replacement": (
                    f"/api/projects/{project_id}/knowledge/source-documents/"
                    f"{document_id}/workflows/{'{workflow_run_id}'}/frontend-events/stream"
                ),
                "bootstrap_snapshot": (
                    f"/api/projects/{project_id}/knowledge/{document_id}/workflow-live-state"
                ),
            },
        )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/{document_id}/resume-processing")
async def resume_knowledge_processing(
    project_id: str,
    document_id: str,
    authorization: str | None = Header(default=None),
    max_drain_commands: int = Query(10, ge=1, le=100),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
    llm_executor: LlmDispatchExecutorPort = Depends(get_llm_dispatch_executor),
):
    """Compatibility alias for the old document-level resume route."""

    return await restore_knowledge_source_document_processing(
        project_id=project_id,
        source_document_ref=document_id,
        authorization=authorization,
        max_drain_commands=max_drain_commands,
        pool=pool,
        project_repo=project_repo,
        user_repo=user_repo,
        llm_executor=llm_executor,
    )


@router.post("/{document_id}/cancel")
async def cancel_knowledge_processing(
    project_id: str,
    document_id: str,
    authorization: str | None = Header(default=None),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
):
    """Cancels active Workbench processing and disables automatic recovery."""

    await _require_project_access(
        project_id=project_id,
        authorization=authorization,
        project_repo=project_repo,
        user_repo=user_repo,
    )
    from src.interfaces.composition.faq_workbench_cancel import (
        WorkbenchCancelProcessingNotFoundError,
        WorkbenchCancelProcessingRejectedError,
        cancel_workbench_processing,
    )

    try:
        return await cancel_workbench_processing(
            pool=pool,
            project_id=project_id,
            document_id=document_id,
        )
    except WorkbenchCancelProcessingNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail="Knowledge document not found",
        ) from exc
    except WorkbenchCancelProcessingRejectedError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc


async def _delete_knowledge_document_by_source_ref(
    *,
    project_id: str,
    source_document_ref: str,
    authorization: str | None,
    pool,
    project_repo,
    user_repo: UserRepository,
) -> dict[str, object]:
    await _require_project_access(
        project_id=project_id,
        authorization=authorization,
        project_repo=project_repo,
        user_repo=user_repo,
    )

    from src.interfaces.http.dependencies import get_current_user_id

    actor_user_id = await get_current_user_id(authorization)
    cleanup_repository = PostgresWorkbenchDocumentRunCleanupRepository(pool)
    use_case = DeleteKnowledgeExtractionDocumentRun(cleanup_repository)

    result = await use_case.execute(
        DeleteKnowledgeExtractionDocumentRunCommand(
            project_id=UUID(project_id),
            source_document_ref=source_document_ref,
            actor_user_id=UUID(str(actor_user_id)),
            occurred_at=datetime.now(timezone.utc),
        )
    )
    if not result.deleted:
        raise HTTPException(status_code=404, detail="Knowledge document not found")

    return {
        "deleted": result.deleted,
        "source_document_ref": result.source_document_ref,
        "document_id": result.source_document_ref,
        "workflow_run_ids": list(result.workflow_run_ids),
        "workflow_run_count": len(result.workflow_run_ids),
        "deleted_counts": result.deleted_counts.to_dict(),
    }


@router.delete("/source-documents/{source_document_ref}")
async def delete_knowledge_source_document(
    project_id: str,
    source_document_ref: str,
    authorization: str | None = Header(default=None),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
):
    """Hard-delete one Workbench source document and every upload/workflow trace."""

    return await _delete_knowledge_document_by_source_ref(
        project_id=project_id,
        source_document_ref=source_document_ref,
        authorization=authorization,
        pool=pool,
        project_repo=project_repo,
        user_repo=user_repo,
    )


@router.delete("/{document_id}")
async def delete_knowledge_document(
    project_id: str,
    document_id: str,
    authorization: str | None = Header(default=None),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
):
    """Compatibility alias for the old document-level delete route."""

    return await _delete_knowledge_document_by_source_ref(
        project_id=project_id,
        source_document_ref=document_id,
        authorization=authorization,
        pool=pool,
        project_repo=project_repo,
        user_repo=user_repo,
    )


async def _list_project_source_document_refs(
    *,
    pool,
    project_id: str,
) -> tuple[str, ...]:
    async with pool.acquire() as connection:
        rows = await connection.fetch(
            """
            SELECT document_ref
            FROM (
                SELECT document_id AS document_ref
                FROM knowledge_workbench_documents
                WHERE project_id = $1::uuid

                UNION

                SELECT document_ref
                FROM source_documents
                WHERE project_id = $2::text
            ) AS refs
            WHERE document_ref IS NOT NULL
            ORDER BY document_ref ASC
            """,
            project_id,
            project_id,
        )

    result: list[str] = []
    for row in rows:
        value = dict(row).get("document_ref")
        if isinstance(value, str) and value.strip():
            result.append(value)
    return tuple(dict.fromkeys(result))


def _deleted_row_count(status: object) -> int:
    if not isinstance(status, str):
        return 0
    parts = status.split()
    if len(parts) != 2 or not parts[1].isdigit():
        return 0
    return int(parts[1])


async def _delete_project_orphan_knowledge_runtime_tails(
    *,
    pool,
    project_id: str,
) -> dict[str, int]:
    """Delete old workflow-runtime tails left by earlier partial document deletes.

    These rows are not protected by source_documents/knowledge_workbench_documents
    FK cascades, but the current workflow_run_id format embeds project_id:
    knowledge-extraction:source-document:{project_id}:...
    """

    workflow_prefix = f"knowledge-extraction:source-document:{project_id}:%"

    async with pool.acquire() as connection:
        async with connection.transaction():
            rows = await connection.fetch(
                """
                SELECT DISTINCT workflow_run_id
                FROM (
                    SELECT workflow_run_id
                    FROM workflow_runtime_timeline_entries
                    WHERE workflow_run_id LIKE $1

                    UNION

                    SELECT workflow_run_id
                    FROM workflow_runtime_command_log
                    WHERE workflow_run_id LIKE $1

                    UNION

                    SELECT workflow_run_id
                    FROM workflow_runtime_outbox_events
                    WHERE workflow_run_id LIKE $1

                    UNION

                    SELECT workflow_run_id
                    FROM workflow_runtime_progress_snapshots
                    WHERE workflow_run_id LIKE $1

                    UNION

                    SELECT workflow_run_id
                    FROM workflow_runtime_resource_usage_snapshots
                    WHERE workflow_run_id LIKE $1
                ) AS runtime_refs
                ORDER BY workflow_run_id ASC
                """,
                workflow_prefix,
            )
            workflow_run_ids = tuple(
                str(dict(row)["workflow_run_id"])
                for row in rows
                if dict(row).get("workflow_run_id") is not None
            )

            frontend_event_status = await connection.execute(
                """
                DELETE FROM frontend_workflow_events
                WHERE project_id = $1
                   OR document_id LIKE $2
                   OR workflow_run_id LIKE $3
                """,
                project_id,
                f"source-document:{project_id}:%",
                workflow_prefix,
            )

            if not workflow_run_ids:
                return {
                    "workflow_commands": 0,
                    "workflow_outbox_events": 0,
                    "workflow_progress_snapshots": 0,
                    "timeline_entries": 0,
                    "resource_usage_snapshots": 0,
                    "frontend_workflow_events": _deleted_row_count(
                        frontend_event_status
                    ),
                }

            outbox_status = await connection.execute(
                """
                DELETE FROM workflow_runtime_outbox_events
                WHERE workflow_run_id = ANY($1::text[])
                """,
                workflow_run_ids,
            )
            command_status = await connection.execute(
                """
                DELETE FROM workflow_runtime_command_log
                WHERE workflow_run_id = ANY($1::text[])
                """,
                workflow_run_ids,
            )
            progress_status = await connection.execute(
                """
                DELETE FROM workflow_runtime_progress_snapshots
                WHERE workflow_run_id = ANY($1::text[])
                """,
                workflow_run_ids,
            )
            timeline_status = await connection.execute(
                """
                DELETE FROM workflow_runtime_timeline_entries
                WHERE workflow_run_id = ANY($1::text[])
                """,
                workflow_run_ids,
            )
            usage_status = await connection.execute(
                """
                DELETE FROM workflow_runtime_resource_usage_snapshots
                WHERE workflow_run_id = ANY($1::text[])
                """,
                workflow_run_ids,
            )
    return {
        "workflow_commands": _deleted_row_count(command_status),
        "workflow_outbox_events": _deleted_row_count(outbox_status),
        "workflow_progress_snapshots": _deleted_row_count(progress_status),
        "timeline_entries": _deleted_row_count(timeline_status),
        "resource_usage_snapshots": _deleted_row_count(usage_status),
        "frontend_workflow_events": _deleted_row_count(frontend_event_status),
    }


@router.delete("")
async def clear_knowledge(
    project_id: str,
    authorization: str | None = Header(default=None),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
):
    """Hard-clear all Workbench documents and every related upload/workflow trace."""

    await _require_project_access(
        project_id=project_id,
        authorization=authorization,
        project_repo=project_repo,
        user_repo=user_repo,
    )

    from src.interfaces.http.dependencies import get_current_user_id

    actor_user_id = await get_current_user_id(authorization)
    cleanup_repository = PostgresWorkbenchDocumentRunCleanupRepository(pool)
    use_case = DeleteKnowledgeExtractionDocumentRun(cleanup_repository)
    source_document_refs = await _list_project_source_document_refs(
        pool=pool,
        project_id=project_id,
    )

    deleted_results: list[dict[str, object]] = []
    total_counts: dict[str, int] = {}

    for source_document_ref in source_document_refs:
        result = await use_case.execute(
            DeleteKnowledgeExtractionDocumentRunCommand(
                project_id=UUID(project_id),
                source_document_ref=source_document_ref,
                actor_user_id=UUID(str(actor_user_id)),
                occurred_at=datetime.now(timezone.utc),
            )
        )
        counts = result.deleted_counts.to_dict()
        for key, value in counts.items():
            total_counts[key] = total_counts.get(key, 0) + value

        deleted_results.append(
            {
                "source_document_ref": result.source_document_ref,
                "document_id": result.source_document_ref,
                "deleted": result.deleted,
                "workflow_run_ids": list(result.workflow_run_ids),
                "deleted_counts": counts,
            }
        )

    orphan_runtime_tail_counts = await _delete_project_orphan_knowledge_runtime_tails(
        pool=pool,
        project_id=project_id,
    )
    for key, value in orphan_runtime_tail_counts.items():
        total_counts[key] = total_counts.get(key, 0) + value

    return {
        "deleted": True,
        "project_id": project_id,
        "deleted_document_count": sum(
            1 for item in deleted_results if item["deleted"] is True
        ),
        "source_document_refs": list(source_document_refs),
        "documents": deleted_results,
        "orphan_runtime_tail_counts": orphan_runtime_tail_counts,
        "deleted_counts": total_counts,
    }


@router.post("/workflows/{workflow_run_id}/pause")
async def pause_knowledge_extraction_workflow(
    project_id: str,
    workflow_run_id: str,
    authorization: str | None = Header(default=None),
    reason: str = Body(default="manual_pause"),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
):
    await _require_project_access(
        project_id=project_id,
        authorization=authorization,
        project_repo=project_repo,
        user_repo=user_repo,
    )

    from src.interfaces.http.dependencies import get_current_user_id

    actor_user_id = await get_current_user_id(authorization)
    runner = make_pause_knowledge_extraction_workflow(pool=pool)

    try:
        result = await runner.execute(
            PauseKnowledgeExtractionWorkflowCommand(
                workflow_run_id=workflow_run_id,
                project_id=project_id,
                actor_user_id=actor_user_id,
                occurred_at=datetime.now(timezone.utc),
                reason=reason,
            )
        )
    except (
        KnowledgeExtractionWorkflowPauseNotFoundError,
        KnowledgeExtractionWorkflowPauseProjectMismatchError,
    ) as exc:
        raise HTTPException(status_code=404, detail="Workflow not found") from exc
    except KnowledgeExtractionWorkflowPauseTerminalStateError as exc:
        raise HTTPException(
            status_code=409,
            detail="Terminal workflow cannot be paused",
        ) from exc

    return {
        "workflow_run_id": result.workflow_run_id,
        "status": result.status,
        "paused_at": result.paused_at.isoformat(),
        "already_paused": result.already_paused,
    }


@router.post("/workflows/{workflow_run_id}/resume")
async def resume_knowledge_extraction_workflow(
    project_id: str,
    workflow_run_id: str,
    authorization: str | None = Header(default=None),
    max_drain_commands: int = Query(10, ge=1, le=100),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
    llm_executor: LlmDispatchExecutorPort = Depends(get_llm_dispatch_executor),
):
    await _require_project_access(
        project_id=project_id,
        authorization=authorization,
        project_repo=project_repo,
        user_repo=user_repo,
    )

    from src.interfaces.http.dependencies import get_current_user_id

    actor_user_id = await get_current_user_id(authorization)
    transition_runner = make_resume_knowledge_extraction_workflow_transition(pool=pool)

    try:
        transition_result = await transition_runner.execute(
            ResumeKnowledgeExtractionWorkflowCommand(
                workflow_run_id=workflow_run_id,
                project_id=project_id,
                actor_user_id=actor_user_id,
                occurred_at=datetime.now(timezone.utc),
                max_drain_commands=max_drain_commands,
            )
        )
        workflow_runner = make_knowledge_extraction_workflow_resume(
            pool=pool,
            llm_executor=llm_executor,
        )
        drain_result = await workflow_runner.execute(
            RunKnowledgeExtractionWorkflowResumeCommand(
                project_id=project_id,
                document_id=workflow_run_id,
                max_drain_commands=max_drain_commands,
            )
        )
    except (
        KnowledgeExtractionWorkflowResumeStateNotFoundError,
        KnowledgeExtractionWorkflowResumeProjectMismatchError,
        KnowledgeExtractionWorkflowResumeNotFoundError,
    ) as exc:
        raise HTTPException(status_code=404, detail="Workflow not found") from exc
    except KnowledgeExtractionWorkflowResumeTerminalStateError as exc:
        raise HTTPException(
            status_code=409,
            detail="Terminal workflow cannot be resumed",
        ) from exc
    except KnowledgeExtractionWorkflowResumeNotPausedError as exc:
        raise HTTPException(
            status_code=409,
            detail="Workflow is not manually paused",
        ) from exc

    return {
        "workflow_run_id": transition_result.workflow_run_id,
        "status": transition_result.status,
        "resumed_at": transition_result.resumed_at.isoformat(),
        "source_document_ref": drain_result.source_document_ref,
        "drained_inspected_count": drain_result.drained_inspected_count,
        "drained_dispatched_count": drain_result.drained_dispatched_count,
        "blocked_command_type": drain_result.blocked_command_type,
        "blocked_reason": drain_result.blocked_reason,
    }


@router.post("/workflows/{workflow_run_id}/confirm-degraded-fallback")
async def confirm_knowledge_extraction_degraded_fallback(
    project_id: str,
    workflow_run_id: str,
    authorization: str | None = Header(default=None),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
):
    await _require_project_access(
        project_id=project_id,
        authorization=authorization,
        project_repo=project_repo,
        user_repo=user_repo,
    )

    from src.interfaces.http.dependencies import get_current_user_id

    actor_user_id = await get_current_user_id(authorization)
    runner = make_knowledge_extraction_degraded_fallback_confirmation(pool=pool)
    try:
        result = await runner.execute(
            ConfirmDraftClaimCompactionDegradedFallbackCommand(
                workflow_run_id=workflow_run_id,
                project_id=project_id,
                actor_user_id=actor_user_id,
                occurred_at=datetime.now(timezone.utc),
            )
        )
    except DraftClaimCompactionDegradedFallbackNotPendingError as exc:
        raise HTTPException(
            status_code=409,
            detail="Degraded fallback confirmation is not pending",
        ) from exc

    return {
        "workflow_run_id": result.workflow_run_id,
        "status": "degraded_fallback_confirmed",
        "degraded_model_ref": result.degraded_model_ref,
        "appended_command_id": result.appended_command_id.value,
    }
