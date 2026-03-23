from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
from uuid import UUID

from src.api.dependencies import (
    get_thread_repo, get_project_repo, get_current_user_id, get_memory_repository
)
from src.database.repositories.thread_repository import ThreadRepository
from src.database.repositories.project_repository import ProjectRepository
from src.database.repositories.memory_repository import MemoryRepository
from src.core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/clients", tags=["clients"])


@router.get("")
async def list_clients(
    project_id: str = Query(..., description="Project ID"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    search: Optional[str] = Query(None, description="Search by name or username"),
    current_user_id: str = Depends(get_current_user_id),
    thread_repo: ThreadRepository = Depends(get_thread_repo),
    project_repo: ProjectRepository = Depends(get_project_repo),
):
    """
    Get paginated list of clients for a project.
    """
    # Verify access
    project = await project_repo.get_project_by_id(project_id)
    if not project or project.get("user_id") != current_user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    # Simple query: select from clients, with optional search
    # We'll implement directly with asyncpg
    async with thread_repo.pool.acquire() as conn:
        where_parts = ["project_id = $1"]
        params = [UUID(project_id)]
        param_idx = 2
        if search:
            where_parts.append(f"(full_name ILIKE ${param_idx} OR username ILIKE ${param_idx})")
            params.append(f"%{search}%")
            param_idx += 1

        where_clause = " AND ".join(where_parts)
        query = f"""
            SELECT id, username, full_name, chat_id, source, created_at
            FROM clients
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """
        params.extend([limit, offset])
        rows = await conn.fetch(query, *params)

        clients = []
        for row in rows:
            clients.append({
                "id": str(row["id"]),
                "username": row["username"],
                "full_name": row["full_name"],
                "chat_id": row["chat_id"],
                "source": row["source"],
                "created_at": row["created_at"]
            })
        return {"clients": clients}


@router.get("/{client_id}")
async def get_client(
    client_id: str,
    project_id: str = Query(..., description="Project ID"),
    current_user_id: str = Depends(get_current_user_id),
    thread_repo: ThreadRepository = Depends(get_thread_repo),
    project_repo: ProjectRepository = Depends(get_project_repo),
    memory_repo: MemoryRepository = Depends(get_memory_repository),
):
    """
    Get detailed client information, including memory.
    """
    # Verify access
    project = await project_repo.get_project_by_id(project_id)
    if not project or project.get("user_id") != current_user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    async with thread_repo.pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT id, username, full_name, chat_id, source, created_at
            FROM clients
            WHERE id = $1 AND project_id = $2
        """, UUID(client_id), UUID(project_id))
        if not row:
            raise HTTPException(status_code=404, detail="Client not found")

        client = {
            "id": str(row["id"]),
            "username": row["username"],
            "full_name": row["full_name"],
            "chat_id": row["chat_id"],
            "source": row["source"],
            "created_at": row["created_at"]
        }

        # Get memory
        memory = await memory_repo.get_for_user(project_id, client_id, limit=100)
        client["memory"] = memory

        # Get threads
        threads = await thread_repo.get_dialogs(project_id, client_id=client_id)
        client["threads"] = threads

        return client
