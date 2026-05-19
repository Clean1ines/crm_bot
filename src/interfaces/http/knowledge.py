"""
API endpoints for managing knowledge base (uploading documents).
"""

from typing import cast

import jwt
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
from pydantic import BaseModel, Field

from src.application.dto.knowledge_dto import (
    KnowledgePreviewRequestDto,
    KnowledgeUploadRequestDto,
)
from src.application.ports.knowledge_port import (
    JwtDecoderPort,
    KnowledgeChunkerPort,
    KnowledgeDbPoolPort,
    KnowledgePreprocessorPort,
    KnowledgeRepositoryPort,
    ModelUsageRepositoryPort,
)
from src.application.services.knowledge_service import (
    KnowledgeService,
    KnowledgeServiceConfig,
)
from src.domain.project_plane.json_types import JsonObject
from src.infrastructure.config.settings import settings
from src.infrastructure.db.repositories.knowledge_repository import KnowledgeRepository
from src.infrastructure.db.repositories.model_usage_repository import (
    ModelUsageRepository,
)
from src.infrastructure.db.repositories.user_repository import UserRepository
from src.infrastructure.llm.chunker import ChunkerService
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


class KnowledgePreviewRequestModel(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    limit: int = Field(default=5, ge=1, le=10)


class KnowledgePipelineCommandRequestModel(BaseModel):
    expected_state: str = Field(min_length=1, max_length=100)
    expected_state_version: int = Field(ge=1)


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


def make_knowledge_repo(pool: KnowledgeDbPoolPort) -> KnowledgeRepositoryPort:
    return cast(KnowledgeRepositoryPort, KnowledgeRepository(pool))


def make_knowledge_preprocessor() -> KnowledgePreprocessorPort:
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
        KnowledgePreviewRequestDto(question=request.question, limit=request.limit),
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


@router.get("/{document_id}/health")
async def knowledge_document_health(
    project_id: str,
    document_id: str,
    authorization: str | None = Header(default=None),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
):
    """Returns pipeline health diagnostics for a knowledge document."""
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
    return await service.document_health(
        project_id=project_id,
        document_id=document_id,
        authorization=authorization,
        knowledge_repo_factory=make_knowledge_repo,
        logger=logger,
    )


@router.get("/{document_id}/inspect")
async def inspect_knowledge_document_pipeline(
    project_id: str,
    document_id: str,
    authorization: str | None = Header(default=None),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
):
    """Returns an operator-focused pipeline inspection payload."""
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
    return await service.inspect_document_pipeline(
        project_id=project_id,
        document_id=document_id,
        authorization=authorization,
        knowledge_repo_factory=make_knowledge_repo,
        logger=logger,
    )


@router.post("/{document_id}/reconcile")
async def reconcile_knowledge_document_pipeline(
    project_id: str,
    document_id: str,
    authorization: str | None = Header(default=None),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
):
    """Runs a safe reconcile diagnostics pass for knowledge pipeline state."""
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
    return await service.reconcile_document_pipeline_state(
        project_id=project_id,
        document_id=document_id,
        authorization=authorization,
        knowledge_repo_factory=make_knowledge_repo,
        logger=logger,
    )


@router.post("/{document_id}/retighten")
async def retighten_knowledge_document(
    project_id: str,
    document_id: str,
    authorization: str | None = Header(default=None),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    queue_repo=Depends(get_queue_repo),
    payload: KnowledgePipelineCommandRequestModel = Body(...),
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
        knowledge_repo_factory=make_knowledge_repo,
        retighten_task_type=TASK_RETIGHTEN_KNOWLEDGE_DOCUMENT,
        expected_state=payload.expected_state,
        expected_state_version=payload.expected_state_version,
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
    payload: KnowledgePipelineCommandRequestModel = Body(...),
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
        knowledge_repo_factory=make_knowledge_repo,
        publish_ready_task_type=TASK_PUBLISH_KNOWLEDGE_READY_ANSWERS,
        expected_state=payload.expected_state,
        expected_state_version=payload.expected_state_version,
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
    payload: KnowledgePipelineCommandRequestModel = Body(...),
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
        knowledge_repo_factory=make_knowledge_repo,
        retry_failed_batches_task_type=TASK_RETRY_KNOWLEDGE_FAILED_BATCHES,
        expected_state=payload.expected_state,
        expected_state_version=payload.expected_state_version,
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


@router.post("")
async def upload_knowledge(
    project_id: str,
    file: UploadFile = File(...),
    preprocessing_mode: str = Form(default="plain"),
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
    - plain: legacy chunk persistence, no LLM preprocessing
    - faq: FAQ normalization
    - price_list: price/menu/catalog normalization
    - instruction: policy/procedure normalization
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
        preprocessor_factory=make_knowledge_preprocessor,
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
