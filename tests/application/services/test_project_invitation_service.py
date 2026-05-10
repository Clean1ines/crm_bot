from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from src.application.services.project_invitation_service import ProjectInvitationService


class FakeAccess:
    async def require_project_role(self, project_id, user_id, allowed_roles):
        return None


class FakeEmailSender:
    def __init__(self, enabled: bool = False) -> None:
        self._enabled = enabled
        self.messages: list[dict[str, str | None]] = []

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def send_email(
        self, *, to_email: str, subject: str, text: str, html: str | None = None
    ) -> None:
        self.messages.append(
            {"to_email": to_email, "subject": subject, "text": text, "html": html}
        )


@dataclass
class FakeUser:
    id: str


class FakeUserRepo:
    def __init__(self) -> None:
        self.identity_user: FakeUser | None = None
        self.linked: list[tuple[str, str, str]] = []
        self.updated: list[tuple[str, dict[str, object]]] = []
        self.verified: list[tuple[str, str]] = []

    async def get_user_by_identity_view(self, provider: str, provider_id: str):
        return self.identity_user

    async def link_identity(
        self, user_id: str, provider: str, provider_id: str
    ) -> bool:
        self.linked.append((user_id, provider, provider_id))
        return True

    async def update_user(self, user_id: str, data: dict[str, object]) -> bool:
        self.updated.append((user_id, data))
        return True

    async def mark_email_verified(self, user_id: str, email: str) -> None:
        self.verified.append((user_id, email))


class FakeProjectRepo:
    def __init__(self, actor_role: str | None = "owner") -> None:
        self.actor_role = actor_role
        self.created: dict[str, object] | None = None
        self.invitation: dict[str, object] | None = None
        self.accepted_token_hash: str | None = None

    async def get_project_member_role(
        self, project_id: str, user_id: str
    ) -> str | None:
        return self.actor_role

    async def create_project_invitation(self, **kwargs):
        self.created = dict(kwargs)
        self.invitation = {
            "id": str(uuid4()),
            "project_id": kwargs["project_id"],
            "email": kwargs["email"],
            "first_name": kwargs["first_name"],
            "last_name": kwargs["last_name"],
            "role": kwargs["role"],
            "invited_by_user_id": kwargs["invited_by_user_id"],
            "expires_at": kwargs["expires_at"].isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "token_hash": kwargs["token_hash"],
        }
        return self.invitation

    async def get_project_invitation_by_token_hash(self, token_hash: str):
        if self.invitation and self.invitation["token_hash"] == token_hash:
            return self.invitation
        return None

    async def accept_project_invitation(
        self, *, token_hash: str, accepted_by_user_id: str
    ):
        self.accepted_token_hash = token_hash
        if not self.invitation or self.invitation["token_hash"] != token_hash:
            return None
        return {
            "id": self.invitation["id"],
            "project_id": self.invitation["project_id"],
            "email": self.invitation["email"],
            "role": self.invitation["role"],
            "accepted_by_user_id": accepted_by_user_id,
        }


def make_service(
    *,
    repo: FakeProjectRepo | None = None,
    user_repo: FakeUserRepo | None = None,
    sender: FakeEmailSender | None = None,
) -> ProjectInvitationService:
    return ProjectInvitationService(
        project_repo=repo or FakeProjectRepo(),
        access_service=FakeAccess(),
        user_repo=user_repo or FakeUserRepo(),
        email_sender=sender or FakeEmailSender(enabled=False),
        frontend_url="https://app.example.test",
    )


@pytest.mark.asyncio
async def test_invite_stores_only_token_hash_and_returns_manual_link_when_email_disabled():
    repo = FakeProjectRepo(actor_role="owner")
    service = make_service(repo=repo)

    result = await service.invite_project_member(
        project_id=str(uuid4()),
        current_user_id=str(uuid4()),
        email="Manager@Example.COM",
        first_name="Ada",
        last_name="Lovelace",
        role="manager",
    )

    assert result["delivery"] == "manual_link"
    assert "project_invite_token=" in str(result["invite_link"])
    assert repo.created is not None
    assert repo.created["email"] == "manager@example.com"
    token_hash = str(repo.created["token_hash"])
    assert len(token_hash) == 64
    assert token_hash not in str(result["invite_link"])


@pytest.mark.asyncio
async def test_owner_can_invite_admin_with_email_delivery_without_returning_link():
    repo = FakeProjectRepo(actor_role="owner")
    sender = FakeEmailSender(enabled=True)
    service = make_service(repo=repo, sender=sender)

    result = await service.invite_project_member(
        project_id=str(uuid4()),
        current_user_id=str(uuid4()),
        email="admin@example.com",
        role="admin",
    )

    assert result["delivery"] == "email"
    assert "invite_link" not in result
    assert len(sender.messages) == 1
    assert "project_invite_token=" in str(sender.messages[0]["text"])


@pytest.mark.asyncio
async def test_admin_can_only_invite_manager():
    service = make_service(repo=FakeProjectRepo(actor_role="admin"))

    with pytest.raises(Exception):
        await service.invite_project_member(
            project_id=str(uuid4()),
            current_user_id=str(uuid4()),
            email="admin@example.com",
            role="admin",
        )

    result = await service.invite_project_member(
        project_id=str(uuid4()),
        current_user_id=str(uuid4()),
        email="manager@example.com",
        role="manager",
    )
    assert result["role"] == "manager"


@pytest.mark.asyncio
async def test_accept_invite_links_email_and_marks_verified_on_current_user():
    repo = FakeProjectRepo(actor_role="owner")
    user_repo = FakeUserRepo()
    service = make_service(repo=repo, user_repo=user_repo)

    invite = await service.invite_project_member(
        project_id=str(uuid4()),
        current_user_id=str(uuid4()),
        email="manager@example.com",
        role="manager",
    )
    token = str(invite["invite_link"]).split("project_invite_token=", 1)[1]
    current_user_id = str(uuid4())

    accepted = await service.accept_project_invitation(
        token=token, current_user_id=current_user_id
    )

    assert accepted["status"] == "accepted"
    assert accepted["user_id"] == current_user_id
    assert user_repo.linked == [(current_user_id, "email", "manager@example.com")]
    assert user_repo.updated == [(current_user_id, {"email": "manager@example.com"})]
    assert user_repo.verified == [(current_user_id, "manager@example.com")]
    assert repo.accepted_token_hash == ProjectInvitationService.hash_token(token)


@pytest.mark.asyncio
async def test_accept_invite_rejects_email_linked_to_another_user():
    repo = FakeProjectRepo(actor_role="owner")
    user_repo = FakeUserRepo()
    user_repo.identity_user = FakeUser(id=str(uuid4()))
    service = make_service(repo=repo, user_repo=user_repo)

    invite = await service.invite_project_member(
        project_id=str(uuid4()),
        current_user_id=str(uuid4()),
        email="manager@example.com",
        role="manager",
    )
    token = str(invite["invite_link"]).split("project_invite_token=", 1)[1]

    with pytest.raises(Exception):
        await service.accept_project_invitation(
            token=token, current_user_id=str(uuid4())
        )
