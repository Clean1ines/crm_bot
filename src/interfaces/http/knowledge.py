"""
Knowledge extraction API boundary.

This router owns the current upload -> source ingestion -> workflow command drain
vertical. Queue-based FAQ Workbench document upload is retired.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from typing import Protocol, cast
from fastapi import (
    APIRouter,
    Body,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    UploadFile,
)

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
from src.contexts.knowledge_workbench.source_management.application.ports.source_management_repository_port import (
    SourceManagementRepositoryPort,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_saga_ports import (
    KnowledgeExtractionSagaStateRepositoryPort,
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
                file_size_bytes
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
                "card_view": None,
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

    embedding_settings = load_embedding_runtime_settings()

    try:
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
    """Returns frontend-facing Workbench workflow live state for one document."""

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
    """Returns Workbench processing progress for one document."""

    await _require_project_access(
        project_id=project_id,
        authorization=authorization,
        project_repo=project_repo,
        user_repo=user_repo,
    )
    from src.interfaces.composition.faq_workbench_progress import (
        WorkbenchProgressNotFoundError,
        fetch_workbench_progress,
    )

    try:
        return await fetch_workbench_progress(
            pool=pool,
            project_id=project_id,
            document_id=document_id,
        )
    except WorkbenchProgressNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail="Knowledge document not found",
        ) from exc


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
    """Returns Workbench evidence trace/source units for one document."""

    await _require_project_access(
        project_id=project_id,
        authorization=authorization,
        project_repo=project_repo,
        user_repo=user_repo,
    )
    from src.interfaces.composition.faq_workbench_evidence_trace import (
        WorkbenchEvidenceTraceNotFoundError,
        fetch_workbench_evidence_trace,
    )

    try:
        return await fetch_workbench_evidence_trace(
            pool=pool,
            project_id=project_id,
            document_id=document_id,
        )
    except WorkbenchEvidenceTraceNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail="Knowledge document not found",
        ) from exc


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


@router.post("/{document_id}/resume-processing")
async def resume_knowledge_processing(
    project_id: str,
    document_id: str,
    authorization: str | None = Header(default=None),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
):
    """Resume the current knowledge-extraction workflow command drain."""

    await _require_project_access(
        project_id=project_id,
        authorization=authorization,
        project_repo=project_repo,
        user_repo=user_repo,
    )

    resume_runner = make_knowledge_extraction_workflow_resume(pool=pool)
    try:
        result = await resume_runner.execute(
            RunKnowledgeExtractionWorkflowResumeCommand(
                project_id=project_id,
                document_id=document_id,
                max_drain_commands=10,
            )
        )
    except KnowledgeExtractionWorkflowResumeNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail="Knowledge extraction workflow not found",
        ) from exc

    return {
        "status": "knowledge_extraction_workflow_resume_requested",
        "workflow_run_id": result.workflow_run_id,
        "source_document_ref": result.source_document_ref,
        "drained_inspected_count": result.drained_inspected_count,
        "drained_dispatched_count": result.drained_dispatched_count,
        "blocked_command_type": result.blocked_command_type,
        "blocked_reason": result.blocked_reason,
    }


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


@router.delete("/{document_id}")
async def delete_knowledge_document(
    project_id: str,
    document_id: str,
    authorization: str | None = Header(default=None),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
):
    """Deletes a Workbench document and invalidates document-scoped processing artifacts."""

    await _require_project_access(
        project_id=project_id,
        authorization=authorization,
        project_repo=project_repo,
        user_repo=user_repo,
    )
    from src.interfaces.composition.faq_workbench_delete import (
        WorkbenchDocumentDeleteNotFoundError,
        WorkbenchDocumentDeleteRejectedError,
        delete_workbench_document,
    )

    try:
        return await delete_workbench_document(
            pool=pool,
            project_id=project_id,
            document_id=document_id,
        )
    except WorkbenchDocumentDeleteNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail="Knowledge document not found",
        ) from exc
    except WorkbenchDocumentDeleteRejectedError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc


@router.delete("")
async def clear_knowledge(
    project_id: str,
    authorization: str | None = Header(default=None),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
):
    """Clears all Workbench knowledge for a project."""

    await _require_project_access(
        project_id=project_id,
        authorization=authorization,
        project_repo=project_repo,
        user_repo=user_repo,
    )
    from src.interfaces.composition.faq_workbench_clear import (
        WorkbenchProjectClearRejectedError,
        clear_workbench_project,
    )

    try:
        return await clear_workbench_project(
            pool=pool,
            project_id=project_id,
        )
    except WorkbenchProjectClearRejectedError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc


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
