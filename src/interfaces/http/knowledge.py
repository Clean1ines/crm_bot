"""
Knowledge extraction API boundary.

This router owns the current upload -> source ingestion -> workflow command drain
vertical. Queue-based FAQ Workbench document upload is retired.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
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
from src.contexts.knowledge_workbench.application.sagas.run_source_ingestion_first_phase import (
    RunSourceIngestionFirstPhaseCommand,
)
from src.contexts.knowledge_workbench.application.sagas.source_ingestion_admission import (
    SourceIngestionActor,
    SourceIngestionAdmissionStatus,
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
from src.interfaces.composition.knowledge_extraction_workflow_resume import (
    KnowledgeExtractionWorkflowResumeNotFoundError,
    RunKnowledgeExtractionWorkflowResumeCommand,
    make_knowledge_extraction_workflow_resume,
)
from src.infrastructure.config.settings import settings
from src.contexts.knowledge_workbench.extraction.application.ports.draft_claim_observation_read_repository_port import (
    DraftClaimObservationReadModel,
)
from src.contexts.knowledge_workbench.extraction.infrastructure.postgres.postgres_draft_claim_observation_read_repository import (
    PostgresDraftClaimObservationReadRepository,
)
from src.contexts.knowledge_workbench.source_management.infrastructure.postgres.postgres_source_management_repository import (
    PostgresSourceManagementRepository,
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
    """Returns Workbench import quality report for one document."""

    await _require_project_access(
        project_id=project_id,
        authorization=authorization,
        project_repo=project_repo,
        user_repo=user_repo,
    )
    from src.interfaces.composition.faq_workbench_import_quality import (
        WorkbenchImportQualityNotFoundError,
        fetch_workbench_import_quality_report,
    )

    try:
        return await fetch_workbench_import_quality_report(
            pool=pool,
            project_id=project_id,
            document_id=document_id,
        )
    except WorkbenchImportQualityNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail="Knowledge document not found",
        ) from exc


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


def _optional_payload_text(payload: dict[str, object], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


@router.post("/{document_id}/surfaces/{surface_id}/approve")
async def approve_knowledge_surface(
    project_id: str,
    document_id: str,
    surface_id: str,
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

    from src.application.workbench_commands.surface_curation import (
        SurfaceCurationRejectedError,
    )
    from src.interfaces.composition.faq_workbench_surface_curation import (
        make_surface_curation_service,
    )

    try:
        service = await make_surface_curation_service(pool)
        return (
            await service.approve_surface(
                project_id=project_id,
                document_id=document_id,
                surface_id=surface_id,
            )
        ).to_dict()
    except SurfaceCurationRejectedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{document_id}/surfaces/{surface_id}/reject")
async def reject_knowledge_surface(
    project_id: str,
    document_id: str,
    surface_id: str,
    payload: dict[str, object] = Body(default_factory=dict),
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

    from src.application.workbench_commands.surface_curation import (
        SurfaceCurationRejectedError,
    )
    from src.interfaces.composition.faq_workbench_surface_curation import (
        make_surface_curation_service,
    )

    try:
        service = await make_surface_curation_service(pool)
        return (
            await service.reject_surface(
                project_id=project_id,
                document_id=document_id,
                surface_id=surface_id,
                reason=str(payload.get("reason") or ""),
            )
        ).to_dict()
    except SurfaceCurationRejectedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.patch("/{document_id}/surfaces/{surface_id}")
async def edit_knowledge_surface(
    project_id: str,
    document_id: str,
    surface_id: str,
    payload: dict[str, object] = Body(default_factory=dict),
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

    from src.application.workbench_commands.surface_curation import (
        SurfaceCurationRejectedError,
    )
    from src.interfaces.composition.faq_workbench_surface_curation import (
        make_surface_curation_service,
    )

    raw_questions = payload.get("question_variants")
    question_variants = (
        tuple(str(item).strip() for item in raw_questions if str(item).strip())
        if isinstance(raw_questions, list)
        else None
    )

    try:
        service = await make_surface_curation_service(pool)
        return (
            await service.edit_surface(
                project_id=project_id,
                document_id=document_id,
                surface_id=surface_id,
                title=_optional_payload_text(payload, "title"),
                answer=_optional_payload_text(payload, "answer"),
                short_answer=_optional_payload_text(payload, "short_answer"),
                question_variants=question_variants,
                retrieval_scope=_optional_payload_text(payload, "retrieval_scope"),
                exclusion_scope=_optional_payload_text(payload, "exclusion_scope"),
            )
        ).to_dict()
    except SurfaceCurationRejectedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{document_id}/facts/{target_fact_id}/merge")
async def merge_knowledge_facts(
    project_id: str,
    document_id: str,
    target_fact_id: str,
    payload: dict[str, object] = Body(default_factory=dict),
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

    from src.application.workbench_commands.surface_curation import (
        SurfaceCurationRejectedError,
    )
    from src.interfaces.composition.faq_workbench_surface_curation import (
        make_surface_curation_service,
    )

    raw_sources = payload.get("source_fact_ids")
    source_fact_ids = (
        tuple(str(item).strip() for item in raw_sources if str(item).strip())
        if isinstance(raw_sources, list)
        else ()
    )

    try:
        service = await make_surface_curation_service(pool)
        return (
            await service.merge_facts(
                project_id=project_id,
                document_id=document_id,
                target_fact_id=target_fact_id,
                source_fact_ids=source_fact_ids,
                reason=str(payload.get("reason") or ""),
            )
        ).to_dict()
    except SurfaceCurationRejectedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.delete("/{document_id}/facts/{fact_id}")
async def delete_knowledge_fact(
    project_id: str,
    document_id: str,
    fact_id: str,
    payload: dict[str, object] = Body(default_factory=dict),
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

    from src.application.workbench_commands.surface_curation import (
        SurfaceCurationRejectedError,
    )
    from src.interfaces.composition.faq_workbench_surface_curation import (
        make_surface_curation_service,
    )

    try:
        service = await make_surface_curation_service(pool)
        return (
            await service.delete_fact(
                project_id=project_id,
                document_id=document_id,
                fact_id=fact_id,
                reason=str(payload.get("reason") or ""),
            )
        ).to_dict()
    except SurfaceCurationRejectedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{document_id}/surfaces/publish-selected")
async def publish_selected_workbench_surfaces(
    project_id: str,
    document_id: str,
    payload: dict[str, object] = Body(default_factory=dict),
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

    from src.application.workbench_commands.surface_curation import (
        SurfaceCurationRejectedError,
    )
    from src.interfaces.composition.faq_workbench_surface_curation import (
        make_surface_curation_service,
    )

    raw_surface_ids = payload.get("surface_ids")
    surface_ids = (
        tuple(str(item).strip() for item in raw_surface_ids if str(item).strip())
        if isinstance(raw_surface_ids, list)
        else ()
    )

    try:
        service = await make_surface_curation_service(pool)
        return (
            await service.publish_selected_surfaces(
                project_id=project_id,
                document_id=document_id,
                surface_ids=surface_ids,
            )
        ).to_dict()
    except SurfaceCurationRejectedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


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
    from src.interfaces.composition.faq_workbench_publish_ready import (
        PublishReadyRejectedError,
        publish_workbench_ready_surfaces,
    )

    try:
        return await publish_workbench_ready_surfaces(
            pool=pool,
            project_id=project_id,
            document_id=document_id,
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail="Knowledge document not found",
        ) from exc
    except PublishReadyRejectedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


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
