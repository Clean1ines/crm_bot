# src/api/chat.py
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

from src.api.dependencies import get_orchestrator, get_project_repo
from src.services.orchestrator import OrchestratorService
from src.database.repositories.project_repository import ProjectRepository
from src.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatMessageRequest(BaseModel):
    message: str
    model: Optional[str] = None


@router.post("/projects/{project_id}")
async def client_chat(
    project_id: str,
    request: ChatMessageRequest,
    orchestrator: OrchestratorService = Depends(get_orchestrator),
    project_repo: ProjectRepository = Depends(get_project_repo)
):
    if not await project_repo.project_exists(project_id):
        raise HTTPException(status_code=404, detail="Project not found")

    async def generate():
        async for chunk in orchestrator.stream_response(project_id, request.message, request.model):
            yield chunk

    return StreamingResponse(generate(), media_type="text/plain")