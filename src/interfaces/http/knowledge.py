"""
API endpoints for managing knowledge base (uploading documents).
"""

from typing import cast

import jwt
from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from src.domain.project_plane.json_types import JsonObject
from src.application.ports.knowledge_port import (
    JwtDecoderPort,
    KnowledgeChunkerPort,
    KnowledgeDbPoolPort,
    KnowledgeRepositoryPort,
)
from src.interfaces.http.dependencies import (
    get_pool,
    get_project_repo,
    get_user_repository,
)
from src.infrastructure.llm.chunker import ChunkerService
from src.infrastructure.db.repositories.knowledge_repository import KnowledgeRepository
from src.infrastructure.db.repositories.user_repository import UserRepository
from src.infrastructure.logging.logger import get_logger
from src.infrastructure.config.settings import settings
from src.application.dto.knowledge_dto import KnowledgePreviewRequestDto
from src.application.services.knowledge_service import KnowledgeService

logger = get_logger(__name__)

router = APIRouter(prefix="/api/projects/{project_id}/knowledge", tags=["knowledge"])


class KnowledgePreviewRequestModel(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    limit: int = Field(default=5, ge=1, le=10)


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
        project_repo, user_repo, pool, settings.JWT_SECRET_KEY, jwt_decoder
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
    user_repo: UserRepository = Depends(get_user_repository),
):
    """
    Returns the best knowledge-base matches for a customer question without
    calling LLM generation.
    """
    service = KnowledgeService(
        project_repo, user_repo, pool, settings.JWT_SECRET_KEY, jwt_decoder
    )
    result = await service.preview_query(
        project_id,
        KnowledgePreviewRequestDto(question=request.question, limit=request.limit),
        authorization,
        knowledge_repo_factory=make_knowledge_repo,
        logger=logger,
    )
    return result.to_dict()


@router.post("")
async def upload_knowledge(
    project_id: str,
    file: UploadFile = File(...),
    authorization: str | None = Header(default=None),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
    user_repo: UserRepository = Depends(get_user_repository),
):
    """
    Загружает текстовый, Markdown, JSON файл или PDF, разбивает на чанки,
    генерирует эмбеддинги и сохраняет в базу знаний проекта.
    """
    service = KnowledgeService(
        project_repo, user_repo, pool, settings.JWT_SECRET_KEY, jwt_decoder
    )
    try:
        file_content = await file.read()
    except Exception as exc:
        logger.error(f"Failed to read uploaded file: {exc}")
        raise HTTPException(status_code=400, detail="Could not read file")
    result = await service.upload(
        project_id,
        file.filename,
        file_content,
        authorization,
        chunker_factory=make_chunker,
        knowledge_repo_factory=make_knowledge_repo,
        logger=logger,
    )
    return result.to_dict()
