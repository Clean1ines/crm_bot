# src/interfaces/http/chat.py
import hashlib

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.interfaces.http.dependencies import (
    get_orchestrator,
    get_project_existence_repo,
)
from src.application.orchestration.conversation_orchestrator import (
    ConversationOrchestrator,
)
from src.application.ports.project_port import ProjectExistencePort
from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatMessageRequest(BaseModel):
    message: str
    model: str | None = None
    visitor_id: str | None = None
    username: str | None = None
    full_name: str | None = None


def _visitor_chat_id(project_id: str, visitor_id: str | None) -> int:
    stable_visitor_id = visitor_id or "anonymous"
    digest = hashlib.sha256(
        f"{project_id}:{stable_visitor_id}".encode("utf-8")
    ).hexdigest()
    return int(digest[:15], 16)


@router.post("/projects/{project_id}")
async def client_chat(
    project_id: str,
    request: ChatMessageRequest,
    orchestrator: ConversationOrchestrator = Depends(get_orchestrator),
    project_repo: ProjectExistencePort = Depends(get_project_existence_repo),
):
    if not await project_repo.project_exists(project_id):
        raise HTTPException(status_code=404, detail="Project not found")

    async def generate():
        response = await orchestrator.process_message(
            project_id=project_id,
            chat_id=_visitor_chat_id(project_id, request.visitor_id),
            text=request.message,
            username=request.username,
            full_name=request.full_name,
            source="web",
        )
        if response:
            yield response

    return StreamingResponse(generate(), media_type="text/plain")
