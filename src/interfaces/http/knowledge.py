"""
API endpoints for managing knowledge base (uploading documents).
"""

from typing import Literal, cast

import jwt
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    UploadFile,
)
from pydantic import BaseModel, Field

from src.application.dto.knowledge_dto import (
    KnowledgePreviewRequestDto,
    KnowledgeUploadRequestDto,
)
from src.application.ports.commercial_price import CommercialPriceKnowledgePort
from src.application.ports.knowledge_port import (
    JwtDecoderPort,
    KnowledgeChunkerPort,
    KnowledgeDbPoolPort,
    KnowledgePreprocessorPort,
    ModelUsageRepositoryPort,
)
from src.application.services.knowledge_processing_report_builder import (
    build_knowledge_processing_report,
)
from src.application.services.knowledge_service import (
    KnowledgeService,
    KnowledgeServiceConfig,
    KnowledgeServiceRepositoryPort,
)
from src.domain.commercial.commercial_truth import CommercialTruthResolutionPolicy
from src.domain.project_plane.json_types import JsonObject
from src.domain.project_plane.knowledge_preprocessing import (
    MODE_FAQ,
    normalize_preprocessing_mode,
)
from src.infrastructure.config.settings import settings
from src.infrastructure.db.repositories.commercial_price_repository import (
    CommercialPriceRepository,
)
from src.infrastructure.db.repositories.knowledge_repository import KnowledgeRepository
from src.infrastructure.db.repositories.model_usage_repository import (
    ModelUsageRepository,
)
from src.infrastructure.db.repositories.user_repository import UserRepository
from src.infrastructure.llm.chunker import ChunkerService
from src.application.services.knowledge_surface_prompt_versions import (
    GRAPH_PROMPT_VERSION,
)
from src.infrastructure.llm.knowledge_preprocessor import GroqKnowledgePreprocessor
from src.infrastructure.logging.logger import get_logger
from src.infrastructure.queue.job_types import (
    TASK_PROCESS_KNOWLEDGE_UPLOAD,
    TASK_PUBLISH_KNOWLEDGE_READY_ANSWERS,
    TASK_RETIGHTEN_KNOWLEDGE_DOCUMENT,
    TASK_RETRY_KNOWLEDGE_FAILED_BATCHES,
)
from src.interfaces.http.dependencies import (
    get_pool,
    get_project_repo,
    get_queue_repo,
    get_user_repository,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/api/projects/{project_id}/knowledge", tags=["knowledge"])
UPLOAD_TOO_LARGE_DETAIL = "Knowledge upload file is too large"


class KnowledgePriceFactsActionRequestModel(BaseModel):
    fact_ids: list[str] = Field(default_factory=list)
    reason: str = Field(default="")


class KnowledgePreviewRequestModel(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    limit: int = Field(default=5, ge=1, le=10)
    retrieval_mode: Literal["runtime_equivalent", "lexical_debug"] = Field(
        default="runtime_equivalent"
    )


class PyJwtDecoder:
    ExpiredSignatureError: type[Exception] = cast(
        type[Exception], jwt.ExpiredSignatureError
    )
    InvalidTokenError: type[Exception] = cast(type[Exception], jwt.InvalidTokenError)

    def decode(
        self,
        token: str,
        secret: str,
        algorithms: list[str],
    ) -> JsonObject:
        return cast(JsonObject, jwt.decode(token, secret, algorithms=algorithms))


jwt_decoder: JwtDecoderPort = PyJwtDecoder()


def make_chunker() -> KnowledgeChunkerPort:
    return cast(KnowledgeChunkerPort, ChunkerService())


def make_knowledge_repo(pool: KnowledgeDbPoolPort) -> KnowledgeServiceRepositoryPort:
    return cast(KnowledgeServiceRepositoryPort, KnowledgeRepository(pool))


def make_commercial_price_repo(
    pool: KnowledgeDbPoolPort,
) -> CommercialPriceKnowledgePort:
    return cast(CommercialPriceKnowledgePort, CommercialPriceRepository(pool))


def make_knowledge_preprocessor(
    *, preprocessing_mode: str
) -> KnowledgePreprocessorPort:
    mode = normalize_preprocessing_mode(preprocessing_mode)
    if mode == MODE_FAQ:
        raise ValueError(
            "Legacy FAQ preprocessor factory is forbidden; FAQ must use surface compiler"
        )
    return cast(KnowledgePreprocessorPort, GroqKnowledgePreprocessor())


def make_model_usage_repo(pool: KnowledgeDbPoolPort) -> ModelUsageRepositoryPort:
    return cast(ModelUsageRepositoryPort, ModelUsageRepository(pool))


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


def _json_int(value: object) -> int:
    if isinstance(value, bool) or value is None:
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return 0


def _json_dict(value: object) -> JsonObject:
    return dict(value) if isinstance(value, dict) else {}


def _overview_is_reportable_document(document: object) -> bool:
    status = str(getattr(document, "status", "") or "")
    preprocessing_status = str(getattr(document, "preprocessing_status", "") or "")
    structured_entries = getattr(document, "structured_entries", 0) or 0
    return (
        status in {"pending", "processing", "error", "cancelled"}
        or preprocessing_status in {"processing", "failed", "cancelled"}
        or int(structured_entries) > 0
    )


def _overview_source_unit_summary(document: object, metrics: JsonObject) -> JsonObject:
    source_unit_count = (
        _json_int(metrics.get("source_unit_count"))
        or _json_int(metrics.get("source_chunk_count"))
        or _json_int(metrics.get("raw_source_chunk_count"))
        or int(getattr(document, "chunk_count", 0) or 0)
    )
    return {
        "source_unit_count": source_unit_count,
        "source_chunk_count": _json_int(metrics.get("source_chunk_count")),
        "raw_source_chunk_count": _json_int(metrics.get("raw_source_chunk_count")),
    }


def _overview_groq_route_summary(metrics: JsonObject) -> JsonObject:
    return {
        key: value
        for key, value in metrics.items()
        if key.startswith("groq_")
        or key
        in {
            "key_slot",
            "actual_model",
            "requested_model",
            "fallback_reason",
            "limit_kind",
            "retry_after_seconds",
            "cooldown_until_epoch",
            "remaining_requests",
            "remaining_tokens",
            "reset_requests_epoch",
            "reset_tokens_epoch",
        }
    }


def _overview_economy_summary(metrics: JsonObject) -> JsonObject:
    return {
        key: metrics.get(key)
        for key in (
            "economy_mode",
            "economy_reason",
            "economy_source_unit_count",
            "economy_source_unit_split_count",
            "economy_subunit_count",
            "economy_completed_subunit_count",
            "economy_quality_warning",
            "quality_mode",
            "quality_warning",
        )
        if key in metrics
    }


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
    """
    Lists uploaded knowledge documents for a project.
    """
    service = KnowledgeService(
        project_repo,
        user_repo,
        pool,
        settings.JWT_SECRET_KEY,
        jwt_decoder,
        service_config=KnowledgeServiceConfig(
            model_usage_monthly_token_budget=int(
                settings.MODEL_USAGE_MONTHLY_TOKEN_BUDGET
            ),
            voyage_free_monthly_tokens=int(settings.VOYAGE_FREE_MONTHLY_TOKENS),
            model_usage_counter_enabled=bool(settings.MODEL_USAGE_COUNTER_ENABLED),
        ),
    )
    await service.require_access(project_id, authorization)

    repo = KnowledgeRepository(pool)
    documents = await repo.get_documents(project_id, limit=limit, offset=offset)
    return {"documents": documents, "items": documents}


@router.get("/processing-overview")
async def knowledge_processing_overview(
    project_id: str,
    authorization: str | None = Header(default=None),
    limit: int = Query(200, ge=1, le=200),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
):
    """Returns one lightweight polling payload for processing knowledge documents."""
    service = KnowledgeService(
        project_repo,
        user_repo,
        pool,
        settings.JWT_SECRET_KEY,
        jwt_decoder,
        service_config=KnowledgeServiceConfig(
            model_usage_monthly_token_budget=int(
                settings.MODEL_USAGE_MONTHLY_TOKEN_BUDGET
            ),
            voyage_free_monthly_tokens=int(settings.VOYAGE_FREE_MONTHLY_TOKENS),
            model_usage_counter_enabled=bool(settings.MODEL_USAGE_COUNTER_ENABLED),
        ),
    )
    await service.require_access(project_id, authorization)

    repo = KnowledgeRepository(pool)
    documents = await repo.get_documents(project_id, limit=limit, offset=0)

    processing_reports: dict[str, JsonObject] = {}
    partial_surface_count: dict[str, int] = {}
    source_unit_summary: dict[str, JsonObject] = {}
    groq_route_summary: dict[str, JsonObject] = {}
    economy_mode_summary: dict[str, JsonObject] = {}

    for document in documents:
        document_id = str(getattr(document, "id", ""))
        if not document_id or not _overview_is_reportable_document(document):
            continue

        batches = await repo.list_document_compiler_batches(
            project_id=project_id,
            document_id=document_id,
        )
        candidate_summary = await repo.get_document_answer_candidate_summary(
            project_id=project_id,
            document_id=document_id,
        )
        report = build_knowledge_processing_report(
            document_id=document_id,
            document=document,
            batches=batches,
            candidate_summary=candidate_summary,
        )
        report_payload = _json_dict(report.to_dict())
        processing_reports[document_id] = report_payload

        metrics = _json_dict(report_payload.get("metrics"))
        partial_surface_count[document_id] = (
            _json_int(metrics.get("retrieval_surface_entry_count"))
            or _json_int(metrics.get("published_answer_count"))
            or _json_int(metrics.get("draft_answer_count"))
            or _json_int(metrics.get("answer_candidate_count"))
        )
        source_unit_summary[document_id] = _overview_source_unit_summary(
            document,
            metrics,
        )
        groq_route_summary[document_id] = _overview_groq_route_summary(metrics)
        economy_mode_summary[document_id] = _overview_economy_summary(metrics)

    return {
        "documents": documents,
        "processing_reports": processing_reports,
        "reports": processing_reports,
        "partial_surface_count": partial_surface_count,
        "source_unit_summary": source_unit_summary,
        "groq_route_summary": groq_route_summary,
        "economy_mode_summary": economy_mode_summary,
    }


@router.post("/preview")
async def preview_knowledge(
    project_id: str,
    request: KnowledgePreviewRequestModel,
    authorization: str | None = Header(default=None),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    queue_repo=Depends(get_queue_repo),
    user_repo: UserRepository = Depends(get_user_repository),
):
    """
    Returns the best knowledge-base matches for a customer question without
    calling LLM generation.
    """
    service = KnowledgeService(
        project_repo,
        user_repo,
        pool,
        settings.JWT_SECRET_KEY,
        jwt_decoder,
        service_config=KnowledgeServiceConfig(
            model_usage_monthly_token_budget=int(
                settings.MODEL_USAGE_MONTHLY_TOKEN_BUDGET
            ),
            voyage_free_monthly_tokens=int(settings.VOYAGE_FREE_MONTHLY_TOKENS),
            model_usage_counter_enabled=bool(settings.MODEL_USAGE_COUNTER_ENABLED),
        ),
    )
    result = await service.preview_query(
        project_id,
        KnowledgePreviewRequestDto(
            question=request.question,
            limit=request.limit,
            retrieval_mode=request.retrieval_mode,
        ),
        authorization,
        knowledge_repo_factory=make_knowledge_repo,
        logger=logger,
    )
    return result.to_dict()


@router.get("/usage")
async def knowledge_usage(
    project_id: str,
    authorization: str | None = Header(default=None),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
):
    service = KnowledgeService(
        project_repo,
        user_repo,
        pool,
        settings.JWT_SECRET_KEY,
        jwt_decoder,
        service_config=KnowledgeServiceConfig(
            model_usage_monthly_token_budget=int(
                settings.MODEL_USAGE_MONTHLY_TOKEN_BUDGET
            ),
            voyage_free_monthly_tokens=int(settings.VOYAGE_FREE_MONTHLY_TOKENS),
            model_usage_counter_enabled=bool(settings.MODEL_USAGE_COUNTER_ENABLED),
        ),
    )
    result = await service.usage(
        project_id,
        authorization,
        model_usage_repo_factory=make_model_usage_repo,
    )
    return result.to_dict()


@router.get("/{document_id}/fragments")
async def knowledge_answer_drafts(
    project_id: str,
    document_id: str,
    authorization: str | None = Header(default=None),
    limit: int = Query(20, ge=1, le=1000),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
):
    """Returns saved answer drafts extracted from a knowledge document."""
    service = KnowledgeService(
        project_repo,
        user_repo,
        pool,
        settings.JWT_SECRET_KEY,
        jwt_decoder,
        service_config=KnowledgeServiceConfig(
            model_usage_monthly_token_budget=int(
                settings.MODEL_USAGE_MONTHLY_TOKEN_BUDGET
            ),
            voyage_free_monthly_tokens=int(settings.VOYAGE_FREE_MONTHLY_TOKENS),
            model_usage_counter_enabled=bool(settings.MODEL_USAGE_COUNTER_ENABLED),
        ),
    )
    result = await service.answer_drafts(
        project_id,
        document_id,
        authorization,
        knowledge_repo_factory=make_knowledge_repo,
        logger=logger,
        limit=limit,
    )
    return result.to_dict()


@router.get("/{document_id}/source-units")
async def knowledge_source_units(
    project_id: str,
    document_id: str,
    authorization: str | None = Header(default=None),
    limit: int = Query(1000, ge=1, le=1000),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
):
    """Returns source units/source chunks used as evidence for a document."""
    service = KnowledgeService(
        project_repo,
        user_repo,
        pool,
        settings.JWT_SECRET_KEY,
        jwt_decoder,
        service_config=KnowledgeServiceConfig(
            model_usage_monthly_token_budget=int(
                settings.MODEL_USAGE_MONTHLY_TOKEN_BUDGET
            ),
            voyage_free_monthly_tokens=int(settings.VOYAGE_FREE_MONTHLY_TOKENS),
            model_usage_counter_enabled=bool(settings.MODEL_USAGE_COUNTER_ENABLED),
        ),
    )
    result = await service.source_units(
        project_id,
        document_id,
        authorization,
        knowledge_repo_factory=make_knowledge_repo,
        logger=logger,
        limit=limit,
    )
    return result.to_dict()


@router.get("/{document_id}/import-quality")
async def knowledge_import_quality_report(
    project_id: str,
    document_id: str,
    authorization: str | None = Header(default=None),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
):
    """Returns a user-facing import quality report for a knowledge document."""
    service = KnowledgeService(
        project_repo,
        user_repo,
        pool,
        settings.JWT_SECRET_KEY,
        jwt_decoder,
        service_config=KnowledgeServiceConfig(
            model_usage_monthly_token_budget=int(
                settings.MODEL_USAGE_MONTHLY_TOKEN_BUDGET
            ),
            voyage_free_monthly_tokens=int(settings.VOYAGE_FREE_MONTHLY_TOKENS),
            model_usage_counter_enabled=bool(settings.MODEL_USAGE_COUNTER_ENABLED),
        ),
    )
    result = await service.import_quality_report(
        project_id,
        document_id,
        authorization,
        knowledge_repo_factory=make_knowledge_repo,
        logger=logger,
    )
    return result.to_dict()


@router.get("/{document_id}/progress")
async def knowledge_processing_progress(
    project_id: str,
    document_id: str,
    authorization: str | None = Header(default=None),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
):
    """Returns a user-facing progress report for knowledge document processing."""
    service = KnowledgeService(
        project_repo,
        user_repo,
        pool,
        settings.JWT_SECRET_KEY,
        jwt_decoder,
        service_config=KnowledgeServiceConfig(
            model_usage_monthly_token_budget=int(
                settings.MODEL_USAGE_MONTHLY_TOKEN_BUDGET
            ),
            voyage_free_monthly_tokens=int(settings.VOYAGE_FREE_MONTHLY_TOKENS),
            model_usage_counter_enabled=bool(settings.MODEL_USAGE_COUNTER_ENABLED),
        ),
    )
    result = await service.processing_report(
        project_id,
        document_id,
        authorization,
        knowledge_repo_factory=make_knowledge_repo,
        logger=logger,
    )
    return result.to_dict()


@router.get("/{document_id}/price-facts")
async def knowledge_price_facts(
    project_id: str,
    document_id: str,
    authorization: str | None = Header(default=None),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
):
    """Returns extracted commercial price facts for review, including non-runtime facts."""
    service = KnowledgeService(
        project_repo,
        user_repo,
        pool,
        settings.JWT_SECRET_KEY,
        jwt_decoder,
        service_config=KnowledgeServiceConfig(
            model_usage_monthly_token_budget=int(
                settings.MODEL_USAGE_MONTHLY_TOKEN_BUDGET
            ),
            voyage_free_monthly_tokens=int(settings.VOYAGE_FREE_MONTHLY_TOKENS),
            model_usage_counter_enabled=bool(settings.MODEL_USAGE_COUNTER_ENABLED),
        ),
    )
    result = await service.price_facts(
        project_id,
        document_id,
        authorization,
        commercial_price_repo_factory=make_commercial_price_repo,
        logger=logger,
    )
    return result.to_dict()


@router.get("/commercial-truth-review")
async def project_commercial_truth_review(
    project_id: str,
    authorization: str | None = Header(default=None),
    policy: CommercialTruthResolutionPolicy = CommercialTruthResolutionPolicy.MANUAL_REVIEW,
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
):
    """Returns project-wide commercial truth conflicts and surface preview."""
    service = KnowledgeService(
        project_repo,
        user_repo,
        pool,
        settings.JWT_SECRET_KEY,
        jwt_decoder,
        service_config=KnowledgeServiceConfig(
            model_usage_monthly_token_budget=int(
                settings.MODEL_USAGE_MONTHLY_TOKEN_BUDGET
            ),
            voyage_free_monthly_tokens=int(settings.VOYAGE_FREE_MONTHLY_TOKENS),
            model_usage_counter_enabled=bool(settings.MODEL_USAGE_COUNTER_ENABLED),
        ),
    )
    result = await service.project_commercial_truth_review(
        project_id,
        authorization,
        commercial_price_repo_factory=make_commercial_price_repo,
        knowledge_repo_factory=make_knowledge_repo,
        logger=logger,
        policy=policy,
    )
    return result.to_dict()


@router.get("/{document_id}/commercial-truth-review")
async def knowledge_commercial_truth_review(
    project_id: str,
    document_id: str,
    authorization: str | None = Header(default=None),
    policy: CommercialTruthResolutionPolicy = CommercialTruthResolutionPolicy.MANUAL_REVIEW,
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
):
    """Returns commercial truth conflicts and surface preview for a price document."""
    service = KnowledgeService(
        project_repo,
        user_repo,
        pool,
        settings.JWT_SECRET_KEY,
        jwt_decoder,
        service_config=KnowledgeServiceConfig(
            model_usage_monthly_token_budget=int(
                settings.MODEL_USAGE_MONTHLY_TOKEN_BUDGET
            ),
            voyage_free_monthly_tokens=int(settings.VOYAGE_FREE_MONTHLY_TOKENS),
            model_usage_counter_enabled=bool(settings.MODEL_USAGE_COUNTER_ENABLED),
        ),
    )
    result = await service.commercial_truth_review(
        project_id,
        document_id,
        authorization,
        commercial_price_repo_factory=make_commercial_price_repo,
        knowledge_repo_factory=make_knowledge_repo,
        logger=logger,
        policy=policy,
    )
    return result.to_dict()


@router.post("/{document_id}/price-facts/publish")
async def publish_knowledge_price_facts(
    project_id: str,
    document_id: str,
    payload: KnowledgePriceFactsActionRequestModel,
    authorization: str | None = Header(default=None),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
):
    """Publishes reviewed commercial price facts for runtime use."""
    service = KnowledgeService(
        project_repo,
        user_repo,
        pool,
        settings.JWT_SECRET_KEY,
        jwt_decoder,
        service_config=KnowledgeServiceConfig(
            model_usage_monthly_token_budget=int(
                settings.MODEL_USAGE_MONTHLY_TOKEN_BUDGET
            ),
            voyage_free_monthly_tokens=int(settings.VOYAGE_FREE_MONTHLY_TOKENS),
            model_usage_counter_enabled=bool(settings.MODEL_USAGE_COUNTER_ENABLED),
        ),
    )
    result = await service.publish_price_facts(
        project_id,
        document_id,
        payload.fact_ids,
        authorization,
        commercial_price_repo_factory=make_commercial_price_repo,
        logger=logger,
    )
    return result.to_dict()


@router.post("/{document_id}/price-facts/reject")
async def reject_knowledge_price_facts(
    project_id: str,
    document_id: str,
    payload: KnowledgePriceFactsActionRequestModel,
    authorization: str | None = Header(default=None),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
):
    """Rejects reviewed commercial price facts without publishing them."""
    service = KnowledgeService(
        project_repo,
        user_repo,
        pool,
        settings.JWT_SECRET_KEY,
        jwt_decoder,
        service_config=KnowledgeServiceConfig(
            model_usage_monthly_token_budget=int(
                settings.MODEL_USAGE_MONTHLY_TOKEN_BUDGET
            ),
            voyage_free_monthly_tokens=int(settings.VOYAGE_FREE_MONTHLY_TOKENS),
            model_usage_counter_enabled=bool(settings.MODEL_USAGE_COUNTER_ENABLED),
        ),
    )
    result = await service.reject_price_facts(
        project_id,
        document_id,
        payload.fact_ids,
        payload.reason,
        authorization,
        commercial_price_repo_factory=make_commercial_price_repo,
        logger=logger,
    )
    return result.to_dict()


@router.post("/{document_id}/retighten")
async def retighten_knowledge_document(
    project_id: str,
    document_id: str,
    authorization: str | None = Header(default=None),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    queue_repo=Depends(get_queue_repo),
    user_repo: UserRepository = Depends(get_user_repository),
):
    """Queues answer resolution tightening for an already processed document."""
    service = KnowledgeService(
        project_repo,
        user_repo,
        pool,
        settings.JWT_SECRET_KEY,
        jwt_decoder,
        service_config=KnowledgeServiceConfig(
            model_usage_monthly_token_budget=int(
                settings.MODEL_USAGE_MONTHLY_TOKEN_BUDGET
            ),
            voyage_free_monthly_tokens=int(settings.VOYAGE_FREE_MONTHLY_TOKENS),
            model_usage_counter_enabled=bool(settings.MODEL_USAGE_COUNTER_ENABLED),
        ),
    )
    return await service.retighten_document_answer_resolution(
        project_id,
        document_id,
        authorization,
        queue_repo=queue_repo,
        retighten_task_type=TASK_RETIGHTEN_KNOWLEDGE_DOCUMENT,
        logger=logger,
    )


@router.post("/{document_id}/publish-ready")
async def publish_knowledge_ready_answers(
    project_id: str,
    document_id: str,
    authorization: str | None = Header(default=None),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    queue_repo=Depends(get_queue_repo),
    user_repo: UserRepository = Depends(get_user_repository),
):
    """Queues publishing of already extracted answer drafts for a document."""
    service = KnowledgeService(
        project_repo,
        user_repo,
        pool,
        settings.JWT_SECRET_KEY,
        jwt_decoder,
        service_config=KnowledgeServiceConfig(
            model_usage_monthly_token_budget=int(
                settings.MODEL_USAGE_MONTHLY_TOKEN_BUDGET
            ),
            voyage_free_monthly_tokens=int(settings.VOYAGE_FREE_MONTHLY_TOKENS),
            model_usage_counter_enabled=bool(settings.MODEL_USAGE_COUNTER_ENABLED),
        ),
    )
    return await service.publish_document_ready_answers(
        project_id,
        document_id,
        authorization,
        queue_repo=queue_repo,
        publish_ready_task_type=TASK_PUBLISH_KNOWLEDGE_READY_ANSWERS,
        logger=logger,
    )


@router.post("/{document_id}/retry-failed-batches")
async def retry_knowledge_failed_batches(
    project_id: str,
    document_id: str,
    authorization: str | None = Header(default=None),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    queue_repo=Depends(get_queue_repo),
    user_repo: UserRepository = Depends(get_user_repository),
):
    """Queues retry for failed durable compiler batches of a document."""
    service = KnowledgeService(
        project_repo,
        user_repo,
        pool,
        settings.JWT_SECRET_KEY,
        jwt_decoder,
        service_config=KnowledgeServiceConfig(
            model_usage_monthly_token_budget=int(
                settings.MODEL_USAGE_MONTHLY_TOKEN_BUDGET
            ),
            voyage_free_monthly_tokens=int(settings.VOYAGE_FREE_MONTHLY_TOKENS),
            model_usage_counter_enabled=bool(settings.MODEL_USAGE_COUNTER_ENABLED),
        ),
    )
    return await service.retry_document_failed_batches(
        project_id,
        document_id,
        authorization,
        queue_repo=queue_repo,
        retry_failed_batches_task_type=TASK_RETRY_KNOWLEDGE_FAILED_BATCHES,
        logger=logger,
    )


@router.post("/{document_id}/resume-processing")
async def resume_knowledge_processing(
    project_id: str,
    document_id: str,
    authorization: str | None = Header(default=None),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    queue_repo=Depends(get_queue_repo),
    user_repo: UserRepository = Depends(get_user_repository),
):
    """Queues explicit resume for a cancelled recoverable FAQ processing run."""
    service = KnowledgeService(
        project_repo,
        user_repo,
        pool,
        settings.JWT_SECRET_KEY,
        jwt_decoder,
        service_config=KnowledgeServiceConfig(
            model_usage_monthly_token_budget=int(
                settings.MODEL_USAGE_MONTHLY_TOKEN_BUDGET
            ),
            voyage_free_monthly_tokens=int(settings.VOYAGE_FREE_MONTHLY_TOKENS),
            model_usage_counter_enabled=bool(settings.MODEL_USAGE_COUNTER_ENABLED),
        ),
    )
    return await service.resume_document_processing(
        project_id,
        document_id,
        authorization,
        knowledge_repo_factory=make_knowledge_repo,
        queue_repo=queue_repo,
        knowledge_upload_task_type=TASK_PROCESS_KNOWLEDGE_UPLOAD,
        expected_faq_surface_prompt_version=GRAPH_PROMPT_VERSION,
        logger=logger,
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
    """Stops queued/running knowledge document processing cooperatively."""
    service = KnowledgeService(
        project_repo,
        user_repo,
        pool,
        settings.JWT_SECRET_KEY,
        jwt_decoder,
        service_config=KnowledgeServiceConfig(
            model_usage_monthly_token_budget=int(
                settings.MODEL_USAGE_MONTHLY_TOKEN_BUDGET
            ),
            voyage_free_monthly_tokens=int(settings.VOYAGE_FREE_MONTHLY_TOKENS),
            model_usage_counter_enabled=bool(settings.MODEL_USAGE_COUNTER_ENABLED),
        ),
    )
    await service.cancel_document_processing(
        project_id,
        document_id,
        authorization,
        knowledge_repo_factory=make_knowledge_repo,
        logger=logger,
    )
    return {"status": "cancelled", "document_id": document_id}


@router.delete("/{document_id}")
async def delete_knowledge_document(
    project_id: str,
    document_id: str,
    authorization: str | None = Header(default=None),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
):
    """Deletes one knowledge document and all artifacts owned by it."""
    service = KnowledgeService(
        project_repo,
        user_repo,
        pool,
        settings.JWT_SECRET_KEY,
        jwt_decoder,
        service_config=KnowledgeServiceConfig(
            model_usage_monthly_token_budget=int(
                settings.MODEL_USAGE_MONTHLY_TOKEN_BUDGET
            ),
            voyage_free_monthly_tokens=int(settings.VOYAGE_FREE_MONTHLY_TOKENS),
            model_usage_counter_enabled=bool(settings.MODEL_USAGE_COUNTER_ENABLED),
        ),
    )
    await service.delete_document(
        project_id,
        document_id,
        authorization,
        knowledge_repo_factory=make_knowledge_repo,
        logger=logger,
    )
    return {"status": "deleted", "document_id": document_id}


@router.post("")
async def upload_knowledge(
    project_id: str,
    file: UploadFile = File(...),
    preprocessing_mode: str = Form(default="faq"),
    authorization: str | None = Header(default=None),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    queue_repo=Depends(get_queue_repo),
    user_repo: UserRepository = Depends(get_user_repository),
):
    """
    Загружает текстовый, Markdown, JSON файл или PDF, разбивает на чанки,
    генерирует эмбеддинги и сохраняет в базу знаний проекта.

    preprocessing_mode:
    - faq: FAQ Retrieval Surface Compilation
    - price_list: price/menu/catalog normalization
    """
    service = KnowledgeService(
        project_repo,
        user_repo,
        pool,
        settings.JWT_SECRET_KEY,
        jwt_decoder,
        service_config=KnowledgeServiceConfig(
            model_usage_monthly_token_budget=int(
                settings.MODEL_USAGE_MONTHLY_TOKEN_BUDGET
            ),
            voyage_free_monthly_tokens=int(settings.VOYAGE_FREE_MONTHLY_TOKENS),
            model_usage_counter_enabled=bool(settings.MODEL_USAGE_COUNTER_ENABLED),
        ),
    )
    try:
        file_content = await _read_upload_bytes(file)
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise
        logger.error(f"Failed to read uploaded file: {exc}")
        raise HTTPException(status_code=400, detail="Could not read file") from exc

    result = await service.upload(
        project_id,
        file.filename,
        file_content,
        authorization,
        chunker_factory=make_chunker,
        knowledge_repo_factory=make_knowledge_repo,
        logger=logger,
        queue_repo=queue_repo,
        knowledge_upload_task_type=TASK_PROCESS_KNOWLEDGE_UPLOAD,
        upload_request=KnowledgeUploadRequestDto(
            preprocessing_mode=preprocessing_mode,
        ),
        preprocessor_factory=(
            lambda: make_knowledge_preprocessor(preprocessing_mode=preprocessing_mode)
        ),
    )
    return result.to_dict()


@router.delete("")
async def clear_knowledge(
    project_id: str,
    authorization: str | None = Header(default=None),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
):
    """Deletes all knowledge documents and chunks for a project."""
    service = KnowledgeService(
        project_repo,
        user_repo,
        pool,
        settings.JWT_SECRET_KEY,
        jwt_decoder,
        service_config=KnowledgeServiceConfig(
            model_usage_monthly_token_budget=int(
                settings.MODEL_USAGE_MONTHLY_TOKEN_BUDGET
            ),
            voyage_free_monthly_tokens=int(settings.VOYAGE_FREE_MONTHLY_TOKENS),
            model_usage_counter_enabled=bool(settings.MODEL_USAGE_COUNTER_ENABLED),
        ),
    )
    await service.clear_project_knowledge(
        project_id,
        authorization,
        knowledge_repo_factory=make_knowledge_repo,
        logger=logger,
    )
    return {"status": "cleared"}
