"""
Template Repository for Workflow Templates.

This module provides data access methods for workflow templates,
which are pre-built graph configurations for quick project setup.
"""

from typing import Any, Dict, List, Optional
from uuid import UUID

import asyncpg

from src.core.logging import get_logger

logger = get_logger(__name__)


class TemplateRepository:
    """
    Repository for managing workflow template operations.
    
    The TemplateRepository handles CRUD operations for workflow
    templates, which allow users to quickly set up projects with
    pre-configured graph structures.
    
    Attributes:
        pool: Asyncpg connection pool for database operations.
    """
    
    def __init__(self, pool: asyncpg.Pool) -> None:
        """
        Initialize the TemplateRepository with a database connection pool.
        
        Args:
            pool: Asyncpg connection pool for database operations.
        """
        self.pool = pool
        logger.debug("TemplateRepository initialized")
    
    async def get_active_templates(self) -> List[Dict[str, Any]]:
        """
        Retrieve all active workflow templates.
        
        Returns only templates that are marked as active, suitable
        for presentation to users during project creation.
        
        Returns:
            List of active templates with id, slug, name, description.
        
        Example:
            >>> templates = await repo.get_active_templates()
            >>> for template in templates:
            ...     print(f"{template['slug']}: {template['name']}")
        """
        logger.debug("Loading active workflow templates")
        
        rows = await self.pool.fetch(
            """
            SELECT id, slug, name, graph_json
            FROM workflow_templates
            WHERE is_active = true
            ORDER BY name
            """
        )
        
        templates = [
            {
                "id": str(row["id"]),
                "slug": row["slug"],
                "name": row["name"],
                "graph_json": row["graph_json"]
            }
            for row in rows
        ]
        
        logger.debug(
            "Active templates loaded",
            extra={"template_count": len(templates)}
        )
        
        return templates
    
    async def get_by_slug(self, slug: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a specific template by its slug.
        
        This method is used when applying a template to a project
        during creation or configuration.
        
        Args:
            slug: The unique slug identifier for the template.
        
        Returns:
            Template data if found, None otherwise.
        
        Example:
            >>> template = await repo.get_by_slug('support')
            >>> if template:
            ...     apply_template_to_project(template)
        """
        logger.debug(
            "Loading template by slug",
            extra={"slug": slug}
        )
        
        row = await self.pool.fetchrow(
            """
            SELECT id, slug, name, graph_json
            FROM workflow_templates
            WHERE slug = $1 AND is_active = true
            """,
            slug
        )
        
        if row is None:
            logger.warning("Template not found", extra={"slug": slug})
            return None
        
        template = {
            "id": str(row["id"]),
            "slug": row["slug"],
            "name": row["name"],
            "graph_json": row["graph_json"]
        }
        
        logger.debug(
            "Template loaded",
            extra={"slug": slug, "template_id": template["id"]}
        )
        
        return template
    
    async def get_by_id(self, template_id: UUID) -> Optional[Dict[str, Any]]:
        """
        Retrieve a specific template by its UUID.
        
        Args:
            template_id: The UUID of the template to retrieve.
        
        Returns:
            Template data if found, None otherwise.
        """
        logger.debug(
            "Loading template by ID",
            extra={"template_id": str(template_id)}
        )
        
        row = await self.pool.fetchrow(
            """
            SELECT id, slug, name, graph_json
            FROM workflow_templates
            WHERE id = $1 AND is_active = true
            """,
            template_id
        )
        
        if row is None:
            logger.warning(
                "Template not found",
                extra={"template_id": str(template_id)}
            )
            return None
        
        template = {
            "id": str(row["id"]),
            "slug": row["slug"],
            "name": row["name"],
            "graph_json": row["graph_json"]
        }
        
        return template
