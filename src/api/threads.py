from fastapi import APIRouter, Depends, HTTPException, Query, Path
from pydantic import BaseModel, Json
from typing import List, Optional
from uuid import UUID

from src.api.dependencies import (
    get_thread_repo, get_event_repo, get_memory_repository, get_project_repo,
    get_current_user_id, get_orchestrator, get_user_repository
)
from src.database.repositories.thread_repository import ThreadRepository
from src.database.repositories.event_repository import EventRepository
from src.database.repositories.memory_repository import MemoryRepository
from src.database.repositories.project_repository import ProjectRepository
from src.database.repositories.user_repository import UserRepository
from src.services.orchestrator import OrchestratorService
from src.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/threads", tags=["threads"])


class ReplyRequest(BaseModel):
    message: str


class UpdateMemoryRequest(BaseModel):
    key: str
    value: Json   # любой JSON-сериализуемый тип


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
    thread_repo: ThreadRepository = Depends(get_thread_repo),
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    """
    Get paginated list of dialogs (threads) for a project.
    Includes client info and last message.
    """
    # Verify user has access to the project
    project = await project_repo.get_project_by_id(project_id)
    if not project or project.get("user_id") != current_user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    dialogs = await thread_repo.get_dialogs(
        project_id=project_id,
        limit=limit,
        offset=offset,
        status_filter=status_filter,
        search=search
    )
    return dialogs


@router.get("/{thread_id}/messages")
async def get_messages(
    thread_id: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user_id: str = Depends(get_current_user_id),
    thread_repo: ThreadRepository = Depends(get_thread_repo),
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    """
    Get paginated messages for a thread.
    """
    # Verify access
    thread = await thread_repo.get_thread_with_project(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    project = await project_repo.get_project_by_id(thread["project_id"])
    if not project or project.get("user_id") != current_user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    messages = await thread_repo.get_messages(thread_id, limit, offset)
    return {"messages": messages}


@router.post("/{thread_id}/reply")
async def reply_to_thread(
    thread_id: str,
    data: ReplyRequest,
    current_user_id: str = Depends(get_current_user_id),
    thread_repo: ThreadRepository = Depends(get_thread_repo),
    project_repo: ProjectRepository = Depends(get_project_repo),
    orchestrator: OrchestratorService = Depends(get_orchestrator),
    user_repo: UserRepository = Depends(get_user_repository),
):
    """
    Send a manager reply to a thread. Only allowed if thread is in manual mode.
    """
    thread = await thread_repo.get_thread_with_project(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    project = await project_repo.get_project_by_id(thread["project_id"])
    if not project or project.get("user_id") != current_user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    if thread["status"] != "manual":
        raise HTTPException(status_code=400, detail="Thread is not in manual mode")

    # Get the user's Telegram chat ID
    user = await user_repo.get_user_by_id(current_user_id)
    if not user or not user.get("telegram_id"):
        raise HTTPException(status_code=400, detail="User has no Telegram account linked")
    manager_chat_id = str(user["telegram_id"])

    # Send reply via orchestrator
    await orchestrator.manager_reply(thread_id, data.message, manager_chat_id)
    return {"status": "sent"}


@router.get("/{thread_id}/timeline")
async def get_timeline(
    thread_id: str,
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user_id: str = Depends(get_current_user_id),
    thread_repo: ThreadRepository = Depends(get_thread_repo),
    event_repo: EventRepository = Depends(get_event_repo),
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    """
    Get paginated timeline of events for a thread (from events table).
    """
    # Verify access
    thread = await thread_repo.get_thread_with_project(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    project = await project_repo.get_project_by_id(thread["project_id"])
    if not project or project.get("user_id") != current_user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    events = await event_repo.get_events_for_thread(thread_id, limit, offset)
    return {"events": events}


@router.get("/{thread_id}/memory")
async def get_memory(
    thread_id: str,
    current_user_id: str = Depends(get_current_user_id),
    thread_repo: ThreadRepository = Depends(get_thread_repo),
    memory_repo: MemoryRepository = Depends(get_memory_repository),
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    """
    Get user memory for the client of this thread.
    """
    # Verify access
    thread = await thread_repo.get_thread_with_project(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    project = await project_repo.get_project_by_id(thread["project_id"])
    if not project or project.get("user_id") != current_user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    client_id = thread.get("client_id")
    if not client_id:
        return {"memory": []}

    memory = await memory_repo.get_for_user(
        project_id=thread["project_id"],
        client_id=client_id,
        limit=100
    )
    return {"memory": memory}


@router.patch("/{thread_id}/memory")
async def update_memory_entry(
    thread_id: str,
    data: UpdateMemoryRequest,
    current_user_id: str = Depends(get_current_user_id),
    thread_repo: ThreadRepository = Depends(get_thread_repo),
    memory_repo: MemoryRepository = Depends(get_memory_repository),
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    """
    Update a specific memory entry for the client of this thread.
    If the key does not exist, it will be created with type 'user_edited'.
    """
    # Verify access
    thread = await thread_repo.get_thread_with_project(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    project = await project_repo.get_project_by_id(thread["project_id"])
    if not project or project.get("user_id") != current_user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    client_id = thread.get("client_id")
    if not client_id:
        raise HTTPException(status_code=400, detail="No client associated with thread")

    await memory_repo.update_by_key(
        project_id=thread["project_id"],
        client_id=client_id,
        key=data.key,
        value=data.value
    )
    return {"status": "updated"}


@router.get("/{thread_id}/state")
async def get_state(
    thread_id: str,
    current_user_id: str = Depends(get_current_user_id),
    thread_repo: ThreadRepository = Depends(get_thread_repo),
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    """
    Get the current state_json (LangGraph state) for the thread.
    """
    # Verify access
    thread = await thread_repo.get_thread_with_project(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    project = await project_repo.get_project_by_id(thread["project_id"])
    if not project or project.get("user_id") != current_user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    state = await thread_repo.get_state_json(thread_id)
    return {"state": state or {}}


@router.post("/{thread_id}/demo")
async def enable_demo_mode(
    thread_id: str,
    current_user_id: str = Depends(get_current_user_id),
    thread_repo: ThreadRepository = Depends(get_thread_repo),
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    """
    Switch the thread to demo mode (interaction_mode='demo').
    """
    # Verify access
    thread = await thread_repo.get_thread_with_project(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    project = await project_repo.get_project_by_id(thread["project_id"])
    if not project or project.get("user_id") != current_user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    await thread_repo.update_interaction_mode(thread_id, "demo")
    return {"status": "demo_enabled"}
