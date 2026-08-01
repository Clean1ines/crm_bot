from collections.abc import Collection

from src.application.ports.project_port import ProjectControlPort

from src.application.errors import ForbiddenError
from src.domain.control_plane.roles import PROJECT_OWNER


class ProjectAccessService:
    """Project access guard for project-scoped permissions."""

    def __init__(self, repo: ProjectControlPort) -> None:
        self.repo = repo

    async def require_project_role(
        self,
        project_id: str,
        user_id: str,
        allowed_roles: Collection[str],
    ) -> None:
        has_role = await self.repo.user_has_project_role(
            project_id, user_id, allowed_roles
        )
        if has_role is True:
            return

        project = await self.repo.get_project_view(project_id)
        if project and project.user_id == str(user_id):
            return

        raise ForbiddenError("Access denied")

    async def resolve_effective_project_role(
        self,
        project_id: str,
        user_id: str,
    ) -> str | None:
        project = await self.repo.get_project_view(project_id)
        if project and project.user_id == str(user_id):
            return PROJECT_OWNER
        return await self.repo.get_project_member_role(project_id, user_id)


ProjectService = ProjectAccessService
