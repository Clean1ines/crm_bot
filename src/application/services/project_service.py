from typing import Any

from src.application.errors import ForbiddenError


class ProjectAccessService:
    """Project access guard for project-scoped permissions."""

    def __init__(self, repo: Any) -> None:
        self.repo = repo

    async def require_project_role(
        self,
        project_id: str,
        user_id: str,
        allowed_roles: list[str],
    ) -> None:
        has_role = await self.repo.user_has_project_role(project_id, user_id, allowed_roles)
        if has_role is True:
            return

        project = await self.repo.get_project_view(project_id)
        if project and project.user_id == str(user_id):
            return

        raise ForbiddenError("Access denied")


ProjectService = ProjectAccessService
