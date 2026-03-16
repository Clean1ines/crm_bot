"""
API endpoints for managing knowledge base (uploading documents).
"""

import uuid
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException

from src.api.dependencies import verify_admin_token, get_pool, get_project_repo
from src.services.chunker import ChunkerService
from src.services.embedding_service import embed_text
from src.database.repositories.knowledge_repository import KnowledgeRepository
from src.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/projects/{project_id}/knowledge", tags=["knowledge"])

@router.post("", dependencies=[Depends(verify_admin_token)])
async def upload_knowledge(
    project_id: str,
    file: UploadFile = File(...),
    pool=Depends(get_pool),
    project_repo=Depends(get_project_repo),
):
    """
    Загружает текстовый файл или PDF, разбивает на чанки, генерирует эмбеддинги
    и сохраняет в базу знаний проекта.
    """
    logger.info(f"Knowledge upload requested for project {project_id}, file: {file.filename}")

    # 1. Проверить существование проекта
    exists = await project_repo.project_exists(project_id)
    if not exists:
        logger.warning(f"Project {project_id} not found")
        raise HTTPException(status_code=404, detail="Project not found")

    # 2. Прочитать файл
    try:
        content = await file.read()
    except Exception as e:
        logger.error(f"Failed to read uploaded file: {e}")
        raise HTTPException(status_code=400, detail="Could not read file")

    # 3. Разбить на чанки
    chunker = ChunkerService()
    try:
        chunks = await chunker.process_file(content, file.filename)
    except ValueError as e:
        logger.error(f"Chunking failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))

    if not chunks:
        logger.warning("No text extracted from file")
        return {"message": "No text extracted", "chunks": 0}

    # 4. Для каждого чанка получить эмбеддинг
    embeddings = []
    for i, chunk in enumerate(chunks):
        logger.debug(f"Generating embedding for chunk {i+1}/{len(chunks)}")
        try:
            emb = await embed_text(chunk)
            embeddings.append(emb)
        except Exception as e:
            logger.error(f"Embedding generation failed for chunk {i+1}: {e}")
            raise HTTPException(status_code=500, detail="Embedding service error")

    # 5. Сохранить в базу
    async with pool.acquire() as conn:
        repo = KnowledgeRepository(conn)
        await repo.add_knowledge_batch(project_id, chunks, embeddings)

    logger.info(f"Successfully uploaded {len(chunks)} chunks to project {project_id}")
    return {"message": f"Uploaded {len(chunks)} chunks", "chunks": len(chunks)}
