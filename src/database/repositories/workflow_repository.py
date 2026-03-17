"""
Workflow Repository for Custom Workflow Storage.

This module provides data access methods for custom workflows,
which are user-created graph configurations for Pro mode projects.
"""

import json
from typing import Any, Dict, List, Optional
from uuid import UUID

import asyncpg

from src.core.logging import get_logger

logger = get_logger(__name__)


class WorkflowRepository:
    """
    Repository for managing custom workflow operations.
    
    The WorkflowRepository handles CRUD operations for custom
    workflows, allowing Pro mode users to create and manage
    their own graph configurations.
    
    Attributes:
        pool: Asyncpg connection pool for database operations.
    """
    
    def __init__(self, pool: asyncpg.Pool) -> None:
        """
        Initialize the WorkflowRepository with a database connection pool.
        
        Args:
            pool: Asyncpg connection pool for database operations.
        """
        self.pool = pool
        logger.debug("WorkflowRepository initialized")
    
    async def get_for_project(
        self,
        project_id: UUID,
        active_only: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Retrieve all workflows for a specific project.
        
        Args:
            project_id: The project ID to filter workflows.
            active_only: If True, only return active workflows.
        
        Returns:
            List of workflows with metadata (excluding graph_json for listing).
        
        Example:
            >>> workflows = await repo.get_for_project(project_id)
            >>> for workflow in workflows:
            ...     print(f"v{workflow['version']}: {workflow['name']}")
        """
        logger.debug(
            "Loading workflows for project",
            extra={"project_id": str(project_id), "active_only": active_only}
        )
        
        if active_only:
            rows = await self.pool.fetch(
                """
                SELECT id, name, description, version, created_at, updated_at
                FROM workflows
                WHERE project_id = $1 AND is_active = true
                ORDER BY version DESC
                """,
                project_id
            )
        else:
            rows = await self.pool.fetch(
                """
                SELECT id, name, description, version, created_at, updated_at
                FROM workflows
                WHERE project_id = $1
                ORDER BY version DESC
                """,
                project_id
            )
        
        workflows = [
            {
                "id": str(row["id"]),
                "name": row["name"],
                "description": row["description"],
                "version": row["version"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"]
            }
            for row in rows
        ]
        
        logger.debug(
            "Workflows loaded",
            extra={"project_id": str(project_id), "workflow_count": len(workflows)}
        )
        
        return workflows
    
    async def get_by_id(
        self,
        workflow_id: UUID,
        include_graph: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve a specific workflow by its UUID.
        
        Args:
            workflow_id: The UUID of the workflow to retrieve.
            include_graph: If True, include graph_json in result.
        
        Returns:
            Workflow data if found, None otherwise.
        """
        logger.debug(
            "Loading workflow by ID",
            extra={"workflow_id": str(workflow_id), "include_graph": include_graph}
        )
        
        if include_graph:
            row = await self.pool.fetchrow(
                """
                SELECT id, project_id, name, description, graph_json, version, is_active
                FROM workflows
                WHERE id = $1
                """,
                workflow_id
            )
        else:
            row = await self.pool.fetchrow(
                """
                SELECT id, project_id, name, description, version, is_active
                FROM workflows
                WHERE id = $1
                """,
                workflow_id
            )
        
        if row is None:
            logger.warning(
                "Workflow not found",
                extra={"workflow_id": str(workflow_id)}
            )
            return None
        
        workflow = {
            "id": str(row["id"]),
            "project_id": str(row["project_id"]),
            "name": row["name"],
            "description": row["description"],
            "version": row["version"],
            "is_active": row["is_active"]
        }
        
        if include_graph:
            workflow["graph_json"] = row["graph_json"]
        
        return workflow
    
    async def save(
        self,
        project_id: UUID,
        name: str,
        graph_json: Dict[str, Any],
        description: Optional[str] = None,
        workflow_id: Optional[UUID] = None
    ) -> UUID:
        """
        Save a workflow (create new or update existing).
        
        If workflow_id is provided, updates the existing workflow
        and increments the version. Otherwise creates a new workflow.
        
        Args:
            project_id: The project ID this workflow belongs to.
            name: Human-readable name for the workflow.
            graph_json: The graph definition from canvas.
            description: Optional description of the workflow.
            workflow_id: Optional ID for update (None for create).
        
        Returns:
            The UUID of the saved workflow.
        
        Raises:
            ValueError: If workflow not found when updating.
        """
        if workflow_id:
            logger.info(
                "Updating workflow",
                extra={"workflow_id": str(workflow_id), "project_id": str(project_id)}
            )
            
            # Increment version on update
            row = await self.pool.fetchrow(
                """
                UPDATE workflows
                SET name = $1,
                    description = $2,
                    graph_json = $3,
                    version = version + 1,
                    updated_at = now()
                WHERE id = $4 AND project_id = $5
                RETURNING id, version
                """,
                name,
                description,
                json.dumps(graph_json),
                workflow_id,
                project_id
            )
            
            if row is None:
                logger.error(
                    "Workflow update failed - not found",
                    extra={"workflow_id": str(workflow_id)}
                )
                raise ValueError(f"Workflow {workflow_id} not found")
            
            logger.info(
                "Workflow updated",
                extra={
                    "workflow_id": str(workflow_id),
                    "new_version": row["version"]
                }
            )
            
            return workflow_id
        else:
            logger.info(
                "Creating new workflow",
                extra={"project_id": str(project_id), "name": name}
            )
            
            row = await self.pool.fetchrow(
                """
                INSERT INTO workflows (project_id, name, description, graph_json)
                VALUES ($1, $2, $3, $4)
                RETURNING id
                """,
                project_id,
                name,
                description,
                json.dumps(graph_json)
            )
            
            new_id = row["id"]
            
            logger.info(
                "Workflow created",
                extra={"workflow_id": str(new_id), "name": name}
            )
            
            return new_id
    
    async def deactivate(self, workflow_id: UUID, project_id: UUID) -> bool:
        """
        Deactivate a workflow (soft delete).
        
        Args:
            workflow_id: The UUID of the workflow to deactivate.
            project_id: The project ID for ownership verification.
        
        Returns:
            True if deactivated, False if not found.
        """
        logger.debug(
            "Deactivating workflow",
            extra={"workflow_id": str(workflow_id), "project_id": str(project_id)}
        )
        
        result = await self.pool.execute(
            """
            UPDATE workflows
            SET is_active = false, updated_at = now()
            WHERE id = $1 AND project_id = $2
            """,
            workflow_id,
            project_id
        )
        
        deactivated = result == "UPDATE 1"
        
        if deactivated:
            logger.info(
                "Workflow deactivated",
                extra={"workflow_id": str(workflow_id)}
            )
        else:
            logger.warning(
                "Workflow deactivation failed - not found",
                extra={"workflow_id": str(workflow_id)}
            )
        
        return deactivated
    
    async def invalidate_cache(self, workflow_id: UUID) -> None:
        """
        Mark a workflow for cache invalidation.
        
        This method is called when a workflow is updated, signaling
        that any cached compiled graphs should be refreshed.
        
        Note: Actual cache invalidation happens in Redis via the
        orchestrator service.
        
        Args:
            workflow_id: The UUID of the workflow that changed.
        """
        logger.debug(
            "Workflow cache invalidation requested",
            extra={"workflow_id": str(workflow_id)}
        )
        # Cache invalidation is handled by the orchestrator via Redis
