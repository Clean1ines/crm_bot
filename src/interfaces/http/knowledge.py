"""
API endpoints for managing knowledge base (uploading documents).
"""

import uuid
import jwt
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Header

from src.interfaces.http.dependencies import get_pool, get_project_repo, get_user_repository
from src.infrastructure.llm.chunker import ChunkerService
from src.infrastructure.db.repositories.knowledge_repository import KnowledgeRepository
from src.infrastructure.db.repositories.user_repository import UserRepository
from src.infrastructure.logging.logger import get_logger
from src.infrastructure.config.settings import settings
from src.application.services.knowledge_service import KnowledgeService

logger = get_logger(__name__)

router = APIRouter(prefix="/api/projects/{project_id}/knowledge", tags=["knowledge"])

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
    Загружает текстовый файл или PDF, разбивает на чанки, генерирует эмбеддинги
    и сохраняет в базу знаний проекта.
    """
    service = KnowledgeService(project_repo, user_repo, pool, settings.JWT_SECRET_KEY, jwt)
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
        chunker_factory=ChunkerService,
        knowledge_repo_factory=KnowledgeRepository,
        logger=logger,
    )
    return result.to_dict()
