"""
Workflows API Router.

This module provides REST API endpoints for managing custom workflows
in Pro mode projects. All endpoints require authentication and
Pro mode verification.
"""

from typing import Any, Dict, List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.api.dependencies import (
    get_pool,
    get_workflow_repo,
    verify_admin_token
)
from src.core.logging import get_logger
from src.database.repositories.workflow_repository import WorkflowRepository

logger = get_logger(__name__)

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


class WorkflowCreateRequest(BaseModel):
    """Request model for creating a new workflow."""
    
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    graph_json: Dict[str, Any] = Field(...)
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "Support Bot v2",
                "description": "Updated support workflow with RAG",
                "graph_json": {
                    "nodes": [
                        {"id": "start", "type": "start"},
                        {"id": "rag", "type": "rag_search"}
                    ],
                    "edges": [["start", "rag"]],
                    "entry_point": "start"
                }
            }
        }


class WorkflowUpdateRequest(BaseModel):
    """Request model for updating an existing workflow."""
    
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    graph_json: Dict[str, Any] = Field(...)


class WorkflowResponse(BaseModel):
    """Response model for workflow operations."""
    
    id: str
    project_id: str
    name: str
    description: str | None
    version: int
    is_active: bool


class WorkflowListResponse(BaseModel):
    """Response model for listing workflows."""
    
    workflows: List[WorkflowResponse]
    total: int


@router.get(
    "/projects/{project_id}",
    response_model=WorkflowListResponse,
    dependencies=[Depends(verify_admin_token)]
)
async def list_workflows(
    project_id: UUID,
    workflow_repo: WorkflowRepository = Depends(get_workflow_repo)
) -> WorkflowListResponse:
    """
    List all workflows for a specific project.
    
    This endpoint returns metadata for all active workflows
    associated with the project (graph_json excluded for performance).
    
    Args:
        project_id: The UUID of the project.
        workflow_repo: Injected workflow repository.
    
    Returns:
        List of workflows with metadata.
    
    Raises:
        HTTPException: If project not found or access denied.
    """
    logger.info(
        "Listing workflows for project",
        extra={"project_id": str(project_id)}
    )
    
    workflows = await workflow_repo.get_for_project(project_id, active_only=True)
    
    return WorkflowListResponse(
        workflows=[WorkflowResponse(**w) for w in workflows],
        total=len(workflows)
    )


@router.post(
    "/projects/{project_id}",
    response_model=WorkflowResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_admin_token)]
)
async def create_workflow(
    project_id: UUID,
    request: WorkflowCreateRequest,
    workflow_repo: WorkflowRepository = Depends(get_workflow_repo)
) -> WorkflowResponse:
    """
    Create a new workflow for a project.
    
    This endpoint creates a new custom workflow. The project must
    be in Pro mode to access this endpoint.
    
    Args:
        project_id: The UUID of the project.
        request: Workflow creation data.
        workflow_repo: Injected workflow repository.
    
    Returns:
        Created workflow metadata.
    
    Raises:
        HTTPException: If validation fails or project not in Pro mode.
    """
    logger.info(
        "Creating workflow for project",
        extra={"project_id": str(project_id), "workflow_name": request.name}
    )
    
    # Validate graph structure (basic)
    if "nodes" not in request.graph_json or "edges" not in request.graph_json:
        logger.warning(
            "Invalid graph structure",
            extra={"project_id": str(project_id)}
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid graph_json: must contain 'nodes' and 'edges'"
        )
    
    try:
        workflow_id = await workflow_repo.save(
            project_id=project_id,
            name=request.name,
            graph_json=request.graph_json,
            description=request.description
        )
        
        workflow = await workflow_repo.get_by_id(workflow_id)
        
        logger.info(
            "Workflow created successfully",
            extra={"workflow_id": str(workflow_id)}
        )
        
        return WorkflowResponse(**workflow)
    
    except Exception as e:
        logger.error(
            "Failed to create workflow",
            extra={"project_id": str(project_id), "error": str(e)}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create workflow"
        )


@router.get(
    "/{workflow_id}",
    response_model=WorkflowResponse,
    dependencies=[Depends(verify_admin_token)]
)
async def get_workflow(
    workflow_id: UUID,
    workflow_repo: WorkflowRepository = Depends(get_workflow_repo)
) -> WorkflowResponse:
    """
    Get a specific workflow by ID.
    
    Args:
        workflow_id: The UUID of the workflow.
        workflow_repo: Injected workflow repository.
    
    Returns:
        Workflow metadata.
    
    Raises:
        HTTPException: If workflow not found.
    """
    logger.debug(
        "Getting workflow",
        extra={"workflow_id": str(workflow_id)}
    )
    
    workflow = await workflow_repo.get_by_id(workflow_id, include_graph=False)
    
    if workflow is None:
        logger.warning(
            "Workflow not found",
            extra={"workflow_id": str(workflow_id)}
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow not found"
        )
    
    return WorkflowResponse(**workflow)


@router.put(
    "/{workflow_id}",
    response_model=WorkflowResponse,
    dependencies=[Depends(verify_admin_token)]
)
async def update_workflow(
    workflow_id: UUID,
    request: WorkflowUpdateRequest,
    workflow_repo: WorkflowRepository = Depends(get_workflow_repo)
) -> WorkflowResponse:
    """
    Update an existing workflow.
    
    This endpoint updates a workflow and increments its version.
    The project must be in Pro mode to access this endpoint.
    
    Args:
        workflow_id: The UUID of the workflow to update.
        request: Updated workflow data.
        workflow_repo: Injected workflow repository.
    
    Returns:
        Updated workflow metadata.
    
    Raises:
        HTTPException: If workflow not found or validation fails.
    """
    logger.info(
        "Updating workflow",
        extra={"workflow_id": str(workflow_id)}
    )
    
    # Validate graph structure
    if "nodes" not in request.graph_json or "edges" not in request.graph_json:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid graph_json: must contain 'nodes' and 'edges'"
        )
    
    # Get existing workflow to verify project_id
    existing = await workflow_repo.get_by_id(workflow_id, include_graph=False)
    
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow not found"
        )
    
    try:
        await workflow_repo.save(
            project_id=UUID(existing["project_id"]),
            name=request.name,
            graph_json=request.graph_json,
            description=request.description,
            workflow_id=workflow_id
        )
        
        updated = await workflow_repo.get_by_id(workflow_id, include_graph=False)
        
        logger.info(
            "Workflow updated successfully",
            extra={"workflow_id": str(workflow_id), "new_version": updated["version"]}
        )
        
        return WorkflowResponse(**updated)
    
    except ValueError as e:
        logger.error(
            "Failed to update workflow",
            extra={"workflow_id": str(workflow_id), "error": str(e)}
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow not found"
        )
    except Exception as e:
        logger.error(
            "Failed to update workflow",
            extra={"workflow_id": str(workflow_id), "error": str(e)}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update workflow"
        )


@router.delete(
    "/{workflow_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(verify_admin_token)]
)
async def delete_workflow(
    workflow_id: UUID,
    workflow_repo: WorkflowRepository = Depends(get_workflow_repo)
) -> None:
    """
    Deactivate (soft delete) a workflow.
    
    This endpoint deactivates a workflow rather than permanently
    deleting it, preserving historical data.
    
    Args:
        workflow_id: The UUID of the workflow to deactivate.
        workflow_repo: Injected workflow repository.
    
    Raises:
        HTTPException: If workflow not found.
    """
    logger.info(
        "Deactivating workflow",
        extra={"workflow_id": str(workflow_id)}
    )
    
    # Get existing workflow to verify project_id
    existing = await workflow_repo.get_by_id(workflow_id, include_graph=False)
    
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow not found"
        )
    
    success = await workflow_repo.deactivate(
        workflow_id=workflow_id,
        project_id=UUID(existing["project_id"])
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workflow not found"
        )
    
    logger.info(
        "Workflow deactivated successfully",
        extra={"workflow_id": str(workflow_id)}
    )
