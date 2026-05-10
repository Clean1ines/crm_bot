"""Application port for project member invitations."""

from typing import Protocol


class ProjectInvitationRepositoryPort(Protocol):
    async def get_project_member_role(
        self, project_id: str, user_id: str
    ) -> str | None: ...

    async def create_project_invitation(
        self,
        *,
        project_id: str,
        email: str,
        first_name: str | None,
        last_name: str | None,
        role: str,
        invited_by_user_id: str,
        token_hash: str,
        expires_at: object,
    ) -> dict[str, object]: ...

    async def get_project_invitation_by_token_hash(
        self,
        token_hash: str,
    ) -> dict[str, object] | None: ...

    async def accept_project_invitation(
        self,
        *,
        token_hash: str,
        accepted_by_user_id: str,
    ) -> dict[str, object] | None: ...
