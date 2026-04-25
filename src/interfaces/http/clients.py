from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional

from src.interfaces.http.dependencies import (
    get_client_query_service,
    get_project_service,
    get_current_user_id,
)
from src.application.services.client_query_service import ClientQueryService
from src.application.services.project_service import ProjectAccessService
from src.domain.control_plane.roles import PROJECT_READ_ROLES
from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/api/clients", tags=["clients"])

@router.get("")
async def list_clients(
    project_id: str = Query(..., description="Project ID"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    search: Optional[str] = Query(None, description="Search by name or username"),
    current_user_id: str = Depends(get_current_user_id),
    client_queries: ClientQueryService = Depends(get_client_query_service),
    project_service: ProjectAccessService = Depends(get_project_service),
):
    """
    Get paginated list of clients for a project.
    """
    # Verify access
    await project_service.require_project_role(project_id, current_user_id, PROJECT_READ_ROLES)

    return await client_queries.list_clients(
        project_id,
        limit=limit,
        offset=offset,
        search=search,
    )


@router.get("/{client_id}")
async def get_client(
    client_id: str,
    project_id: str = Query(..., description="Project ID"),
    current_user_id: str = Depends(get_current_user_id),
    client_queries: ClientQueryService = Depends(get_client_query_service),
    project_service: ProjectAccessService = Depends(get_project_service),
):
    """
    Get detailed client information, including memory.
    """
    # Verify access
    await project_service.require_project_role(project_id, current_user_id, PROJECT_READ_ROLES)

    client = await client_queries.get_client_detail(project_id, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    return client
