from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Json

from src.application.orchestration.conversation_orchestrator import (
    ConversationOrchestrator,
)
from src.application.services.ticket_command_service import TicketCommandService
from src.application.services.thread_command_service import ThreadCommandService
from src.application.services.thread_query_service import ThreadQueryService
from src.infrastructure.logging.logger import get_logger
from src.interfaces.http.dependencies import (
    get_current_user_id,
    get_orchestrator,
    get_thread_command_service,
    get_thread_query_service,
    get_ticket_command_service,
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
    last_message: dict | None
    unread_count: int


class ThreadActionResponse(BaseModel):
    status: str


@router.get("", response_model=list[ThreadResponse])
async def list_dialogs(
    project_id: str = Query(..., description="Project ID to filter threads"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status_filter: str | None = Query(
        None,
        description=(
            "Filter by thread status (active, waiting_manager, manual, closed, manager)"
        ),
    ),
    search: str | None = Query(None, description="Search by client name or username"),
    current_user_id: str = Depends(get_current_user_id),
    thread_queries: ThreadQueryService = Depends(get_thread_query_service),
):
    """
    Get paginated list of dialogs (threads) for a project.
    Includes client info and last message.
    """
    dialogs = await thread_queries.list_dialogs(
        project_id=project_id,
        limit=limit,
        offset=offset,
        status_filter=status_filter,
        search=search,
        current_user_id=current_user_id,
    )
    return [
        dialog.to_record() if hasattr(dialog, "to_record") else dialog
        for dialog in dialogs
    ]


@router.get("/{thread_id}/messages")
async def get_messages(
    thread_id: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user_id: str = Depends(get_current_user_id),
    thread_queries: ThreadQueryService = Depends(get_thread_query_service),
):
    """Get paginated messages for a thread."""
    return await thread_queries.get_messages_for_user(
        thread_id, current_user_id, limit, offset
    )


@router.post("/{thread_id}/reply")
async def reply_to_thread(
    thread_id: str,
    data: ReplyRequest,
    current_user_id: str = Depends(get_current_user_id),
    thread_queries: ThreadQueryService = Depends(get_thread_query_service),
    orchestrator: ConversationOrchestrator = Depends(get_orchestrator),
    ticket_commands: TicketCommandService = Depends(get_ticket_command_service),
):
    """Send a manager reply to a thread while it is in manual mode."""
    await thread_queries.get_manual_reply_thread_for_user(thread_id, current_user_id)

    await orchestrator.manager_reply(
        thread_id,
        data.message,
        manager_chat_id=None,
        manager_user_id=current_user_id,
    )
    await ticket_commands.mark_ticket_replied(
        thread_id=thread_id,
        manager_user_id=current_user_id,
    )
    return {"status": "sent"}


@router.post("/{thread_id}/claim", response_model=ThreadActionResponse)
async def claim_thread(
    thread_id: str,
    current_user_id: str = Depends(get_current_user_id),
    thread_queries: ThreadQueryService = Depends(get_thread_query_service),
    ticket_commands: TicketCommandService = Depends(get_ticket_command_service),
):
    """Claim a waiting ticket for a manager in the web panel."""
    thread = await thread_queries.require_thread_access(
        thread_id,
        current_user_id,
        ["owner", "admin", "manager"],
    )
    if thread.status == "closed":
        return {"status": "closed"}
    if thread.status == "manual" and thread.manager_user_id == current_user_id:
        return {"status": "claimed"}
    return await ticket_commands.claim_ticket(
        thread_id=thread_id,
        manager_user_id=current_user_id,
    )


@router.post("/{thread_id}/close", response_model=ThreadActionResponse)
async def close_thread(
    thread_id: str,
    current_user_id: str = Depends(get_current_user_id),
    thread_queries: ThreadQueryService = Depends(get_thread_query_service),
    ticket_commands: TicketCommandService = Depends(get_ticket_command_service),
):
    """Close a ticket from the web panel and return the next client message to AI."""
    thread = await thread_queries.require_thread_access(
        thread_id,
        current_user_id,
        ["owner", "admin", "manager"],
    )
    if thread.status == "closed":
        return {"status": "closed"}
    return await ticket_commands.close_ticket(thread_id=thread_id)


@router.get("/{thread_id}/timeline")
async def get_timeline(
    thread_id: str,
    limit: int = Query(30, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user_id: str = Depends(get_current_user_id),
    thread_queries: ThreadQueryService = Depends(get_thread_query_service),
):
    """Get paginated timeline of events for a thread."""
    return await thread_queries.get_timeline_for_user(
        thread_id, current_user_id, limit, offset
    )


@router.get("/{thread_id}/memory")
async def get_memory(
    thread_id: str,
    current_user_id: str = Depends(get_current_user_id),
    thread_queries: ThreadQueryService = Depends(get_thread_query_service),
):
    """Get client memory for this thread."""
    return await thread_queries.get_memory_for_user(
        thread_id, current_user_id, limit=100
    )


@router.patch("/{thread_id}/memory")
async def update_memory_entry(
    thread_id: str,
    data: UpdateMemoryRequest,
    current_user_id: str = Depends(get_current_user_id),
    thread_commands: ThreadCommandService = Depends(get_thread_command_service),
    thread_queries: ThreadQueryService = Depends(get_thread_query_service),
):
    """
    Update a specific memory entry for the client of this thread.
    If the key does not exist, it will be created with type 'user_edited'.
    """
    thread = await thread_queries.get_memory_update_target_for_user(
        thread_id, current_user_id
    )

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
):
    """Get the persisted LangGraph state for a thread."""
    return await thread_queries.get_state_for_user(thread_id, current_user_id)
