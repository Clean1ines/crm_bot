"""Application service for project member email/link invitations."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from src.application.ports.email_port import EmailSenderPort
from src.application.ports.project_invitation_port import (
    ProjectInvitationRepositoryPort,
)
from src.application.ports.project_port import ProjectAccessPort
from src.application.ports.user_port import UserRepositoryPort
from src.domain.control_plane.memberships import normalize_project_role
from src.application.errors import ValidationError
from src.domain.identity.auth_providers import (
    AUTH_DELIVERY_EMAIL,
    AUTH_DELIVERY_MANUAL_LINK,
    AUTH_PROVIDER_EMAIL,
)
from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)

INVITABLE_PROJECT_ROLES = frozenset({"admin", "manager"})
DEFAULT_INVITE_TTL_HOURS = 72


class ProjectInvitationService:
    def __init__(
        self,
        *,
        project_repo: ProjectInvitationRepositoryPort,
        access_service: ProjectAccessPort,
        user_repo: UserRepositoryPort,
        email_sender: EmailSenderPort | None,
        frontend_url: str,
    ) -> None:
        self.project_repo = project_repo
        self.access_service = access_service
        self.user_repo = user_repo
        self.email_sender = email_sender
        self.frontend_url = frontend_url.rstrip("/")

    async def invite_project_member(
        self,
        *,
        project_id: str,
        current_user_id: str,
        email: str,
        first_name: str | None = None,
        last_name: str | None = None,
        role: str = "manager",
    ) -> dict[str, object]:
        await self.access_service.require_project_role(
            project_id,
            current_user_id,
            ["owner", "admin"],
        )

        normalized_email = self._normalize_email(email)
        normalized_role = self._normalize_invite_role(role)
        actor_role = await self.project_repo.get_project_member_role(
            project_id, current_user_id
        )
        self._enforce_invite_permission(actor_role, normalized_role)

        raw_token = secrets.token_urlsafe(32)
        token_hash = self.hash_token(raw_token)
        expires_at = datetime.now(timezone.utc) + timedelta(
            hours=DEFAULT_INVITE_TTL_HOURS
        )

        invitation = await self.project_repo.create_project_invitation(
            project_id=project_id,
            email=normalized_email,
            first_name=self._clean_optional(first_name),
            last_name=self._clean_optional(last_name),
            role=normalized_role,
            invited_by_user_id=current_user_id,
            token_hash=token_hash,
            expires_at=expires_at,
        )

        invite_link = self._build_invite_link(raw_token)
        delivery = await self._send_invitation_email(
            to_email=normalized_email,
            invite_link=invite_link,
            role=normalized_role,
        )

        payload: dict[str, object] = {
            "status": "invited",
            "project_id": str(invitation["project_id"]),
            "email": normalized_email,
            "role": normalized_role,
            "expires_at": str(invitation["expires_at"]),
            "delivery": delivery,
        }
        if delivery == AUTH_DELIVERY_MANUAL_LINK:
            payload["invite_link"] = invite_link
        return payload

    async def accept_project_invitation(
        self,
        *,
        token: str,
        current_user_id: str,
    ) -> dict[str, object]:
        token_value = token.strip()
        if not token_value:
            raise ValidationError("Invite token is required")

        token_hash = self.hash_token(token_value)
        invitation = await self.project_repo.get_project_invitation_by_token_hash(
            token_hash
        )
        if not invitation:
            raise ValidationError("Invalid or expired invite token")

        email = self._normalize_email(str(invitation["email"]))
        existing_email_user = await self.user_repo.get_user_by_identity_view(
            AUTH_PROVIDER_EMAIL, email
        )
        if existing_email_user and str(existing_email_user.id) != str(current_user_id):
            raise ValidationError("Invite email is already linked to another account")

        await self.user_repo.link_identity(current_user_id, AUTH_PROVIDER_EMAIL, email)
        await self.user_repo.update_user(current_user_id, {"email": email})
        await self.user_repo.mark_email_verified(current_user_id, email)

        accepted = await self.project_repo.accept_project_invitation(
            token_hash=token_hash,
            accepted_by_user_id=current_user_id,
        )
        if not accepted:
            raise ValidationError("Invalid or expired invite token")

        return {
            "status": "accepted",
            "project_id": str(accepted["project_id"]),
            "user_id": current_user_id,
            "email": email,
            "role": str(accepted["role"]),
        }

    @staticmethod
    def hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _normalize_email(email: str) -> str:
        normalized = email.strip().lower()
        if not normalized or "@" not in normalized:
            raise ValidationError("Valid email is required")
        return normalized

    @staticmethod
    def _clean_optional(value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @staticmethod
    def _normalize_invite_role(role: str) -> str:
        normalized = normalize_project_role(role)
        if normalized not in INVITABLE_PROJECT_ROLES:
            raise ValidationError("Only admin and manager roles can be invited")
        return normalized

    @staticmethod
    def _enforce_invite_permission(actor_role: str | None, invited_role: str) -> None:
        if actor_role == "owner":
            return
        if actor_role == "admin" and invited_role == "manager":
            return
        raise ValidationError("Insufficient project role for this invitation")

    def _build_invite_link(self, token: str) -> str:
        query = urlencode({"project_invite_token": token})
        if self.frontend_url:
            return f"{self.frontend_url}/login?{query}"
        return f"/login?{query}"

    async def _send_invitation_email(
        self,
        *,
        to_email: str,
        invite_link: str,
        role: str,
    ) -> str:
        if self.email_sender is None or not self.email_sender.enabled:
            return AUTH_DELIVERY_MANUAL_LINK

        try:
            await self.email_sender.send_email(
                to_email=to_email,
                subject="Project invitation",
                text=(
                    f"You have been invited to join a project as {role}.\n\n"
                    f"Open this link to accept the invitation:\n{invite_link}\n\n"
                    "If you did not expect this invitation, ignore this email."
                ),
                html=(
                    f"<p>You have been invited to join a project as <b>{role}</b>.</p>"
                    f'<p><a href="{invite_link}">Accept invitation</a></p>'
                    "<p>If you did not expect this invitation, ignore this email.</p>"
                ),
            )
        except Exception as exc:
            logger.warning(
                "Project invitation email delivery failed; falling back to manual link",
                extra={"to_email": to_email, "error_type": type(exc).__name__},
            )
            return AUTH_DELIVERY_MANUAL_LINK

        return AUTH_DELIVERY_EMAIL
