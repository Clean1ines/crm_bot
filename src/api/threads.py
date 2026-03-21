from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional
from uuid import UUID

from src.api.dependencies import get_thread_repo, get_orchestrator, verify_admin_token
from src.database.repositories.thread_repository import ThreadRepository
from src.services.orchestrator import OrchestratorService
from src.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/threads", tags=["threads"])


class ThreadResponse(BaseModel):
    id: str
    client_id: str
    project_id: str
    status: str
    created_at: str
    updated_at: str
    last_message: Optional[str]
    client_name: Optional[str]  # можно получить из clients таблицы


@router.get("", response_model=List[ThreadResponse], dependencies=[Depends(verify_admin_token)])
async def list_threads(
    status: Optional[str] = Query(None, description="Фильтр по статусу (например, 'manual')"),
    thread_repo: ThreadRepository = Depends(get_thread_repo)
):
    """Возвращает список тредов. Для менеджерского портала обычно status=manual."""
    if status:
        threads = await thread_repo.find_by_status(status)
    else:
        threads = await thread_repo.get_all()  # если такой метод есть
    # Дополнительно можно подтянуть имена клиентов (JOIN с clients)
    return threads


class ReplyRequest(BaseModel):
    message: str


@router.post("/{thread_id}/reply", dependencies=[Depends(verify_admin_token)])
async def reply_to_thread(
    thread_id: str,
    data: ReplyRequest,
    thread_repo: ThreadRepository = Depends(get_thread_repo),
    orchestrator: OrchestratorService = Depends(get_orchestrator)
):
    """Отправляет ответ менеджера в указанный тред."""
    thread = await thread_repo.get_by_id(thread_id)
    if not thread or thread["status"] != "manual":
        raise HTTPException(status_code=400, detail="Thread not in manual mode")

    # Отправляем ответ клиенту через orchestrator
    await orchestrator.manager_reply(thread_id, data.message)
    return {"status": "sent"}