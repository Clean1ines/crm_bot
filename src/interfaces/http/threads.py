from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Json

from src.application.orchestration.conversation_orchestrator import ConversationOrchestrator
from src.application.services.project_service import ProjectAccessService
from src.application.services.thread_command_service import ThreadCommandService
from src.application.services.thread_query_service import ThreadQueryService
from src.domain.control_plane.roles import PROJECT_OWNER, PROJECT_READ_ROLES, PROJECT_WRITE_ROLES
from src.infrastructure.logging.logger import get_logger
from src.interfaces.http.dependencies import (
    get_current_user_id,
    get_orchestrator,
    get_project_service,
    get_thread_command_service,
    get_thread_query_service,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/api/threads", tags=["threads"])


class ReplyRequest(BaseModel):
    message: str


class UpdateMemoryRequest(BaseModel):
    key: str
    value: Json


class ThreadResponse(BaseModel):
    thread_id: str
    status: str
    interaction_mode: str
    thread_created_at: str
    thread_updated_at: str
    client: dict
    last_message: Optional[dict]
    unread_count: int


@router.get("", response_model=List[ThreadResponse])
async def list_dialogs(
    project_id: str = Query(..., description="Project ID to filter threads"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status_filter: Optional[str] = Query(None, description="Filter by thread status (active, manual, closed)"),
    search: Optional[str] = Query(None, description="Search by client name or username"),
    current_user_id: str = Depends(get_current_user_id),
    thread_queries: ThreadQueryService = Depends(get_thread_query_service),
    project_service: ProjectAccessService = Depends(get_project_service),
):
    """
    Get paginated list of dialogs (threads) for a project.
    Includes client info and last message.
    """
    await project_service.require_project_role(project_id, current_user_id, PROJECT_READ_ROLES)
    return await thread_queries.list_dialogs(
        project_id=project_id,
        limit=limit,
        offset=offset,
        status_filter=status_filter,
        search=search,
    )


@router.get("/{thread_id}/messages")
async def get_messages(
    thread_id: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user_id: str = Depends(get_current_user_id),
    thread_queries: ThreadQueryService = Depends(get_thread_query_service),
    project_service: ProjectAccessService = Depends(get_project_service),
):
    """Get paginated messages for a thread."""
    thread = await thread_queries.get_thread_view(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    await project_service.require_project_role(thread.project_id, current_user_id, PROJECT_READ_ROLES)
    return await thread_queries.get_messages(thread_id, limit, offset)


@router.post("/{thread_id}/reply")
async def reply_to_thread(
    thread_id: str,
    data: ReplyRequest,
    current_user_id: str = Depends(get_current_user_id),
    thread_queries: ThreadQueryService = Depends(get_thread_query_service),
    project_service: ProjectAccessService = Depends(get_project_service),
    orchestrator: ConversationOrchestrator = Depends(get_orchestrator),
):
    """Send a manager reply to a thread while it is in manual mode."""
    thread = await thread_queries.get_thread_view(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    await project_service.require_project_role(thread.project_id, current_user_id, PROJECT_WRITE_ROLES)

    if thread.status != "manual":
        raise HTTPException(status_code=400, detail="Thread is not in manual mode")

    await orchestrator.manager_reply(
        thread_id,
        data.message,
        manager_chat_id=None,
        manager_user_id=current_user_id,
    )
    return {"status": "sent"}


@router.get("/{thread_id}/timeline")
async def get_timeline(
    thread_id: str,
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user_id: str = Depends(get_current_user_id),
    thread_queries: ThreadQueryService = Depends(get_thread_query_service),
    project_service: ProjectAccessService = Depends(get_project_service),
):
    """Get paginated timeline of events for a thread."""
    thread = await thread_queries.get_thread_view(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    await project_service.require_project_role(thread.project_id, current_user_id, PROJECT_READ_ROLES)
    return await thread_queries.get_timeline(thread_id, limit, offset)


@router.get("/{thread_id}/memory")
async def get_memory(
    thread_id: str,
    current_user_id: str = Depends(get_current_user_id),
    thread_queries: ThreadQueryService = Depends(get_thread_query_service),
    project_service: ProjectAccessService = Depends(get_project_service),
):
    """Get client memory for this thread."""
    thread = await thread_queries.get_thread_view(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    await project_service.require_project_role(thread.project_id, current_user_id, PROJECT_READ_ROLES)
    return await thread_queries.get_memory(thread.project_id, thread.client_id, limit=100)


@router.patch("/{thread_id}/memory")
async def update_memory_entry(
    thread_id: str,
    data: UpdateMemoryRequest,
    current_user_id: str = Depends(get_current_user_id),
    thread_commands: ThreadCommandService = Depends(get_thread_command_service),
    project_service: ProjectAccessService = Depends(get_project_service),
    thread_queries: ThreadQueryService = Depends(get_thread_query_service),
):
    """
    Update a specific memory entry for the client of this thread.
    If the key does not exist, it will be created with type 'user_edited'.
    """
    thread = await thread_queries.get_thread_view(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    await project_service.require_project_role(thread.project_id, current_user_id, PROJECT_READ_ROLES)

    if not thread.client_id:
        raise HTTPException(status_code=400, detail="No client associated with thread")

    return await thread_commands.update_memory_entry(
        project_id=thread.project_id,
        client_id=thread.client_id,
        key=data.key,
        value=data.value,
    )


@router.get("/{thread_id}/state")
async def get_state(
    thread_id: str,
    current_user_id: str = Depends(get_current_user_id),
    thread_queries: ThreadQueryService = Depends(get_thread_query_service),
    project_service: ProjectAccessService = Depends(get_project_service),
):
    """Get the persisted LangGraph state for a thread."""
    thread = await thread_queries.get_thread_view(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    await project_service.require_project_role(thread.project_id, current_user_id, PROJECT_READ_ROLES)
    return await thread_queries.get_state(thread_id)


