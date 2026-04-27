from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Mapping, cast

import jwt

from src.application.dto.auth_dto import (
    AuthActionDto,
    AuthMethodsDto,
    AuthSessionDto,
    UserProfileDto,
)
from src.application.errors import ConflictError, NotFoundError, UnauthorizedError, ValidationError
from src.application.ports.google_identity_port import GoogleIdentityClaims, GoogleIdentityVerifier
from src.application.ports.user_port import UserRepositoryPort
from src.domain.identity.auth_providers import (
    ALLOWED_AUTH_PROVIDERS,
    AUTH_DELIVERY_MANUAL_LINK,
    AUTH_PROVIDER_EMAIL,
    AUTH_PROVIDER_GOOGLE,
    AUTH_STATUS_PASSWORD_RESET_COMPLETED,
    AUTH_STATUS_PASSWORD_RESET_REQUESTED,
    AUTH_STATUS_VERIFICATION_REQUESTED,
    EMAIL_VERIFICATION_QUERY_KEY,
    PASSWORD_RESET_QUERY_KEY,
)
from src.domain.project_plane.json_types import JsonObject
from src.domain.identity.user_views import AuthMethodsView, UserProfileView


@dataclass(frozen=True, slots=True)
class AuthConfig:
    jwt_secret_key: str
    frontend_url: str | None = None
    public_url: str | None = None
    render_external_url: str | None = None
    google_client_id: str | None = None



def _payload_get(payload, key: str, default=None):
    if isinstance(payload, dict):
        return payload.get(key, default)
    return getattr(payload, key, default)


class AuthService:
    def __init__(
        self,
        user_repo: UserRepositoryPort,
        *,
        config: AuthConfig,
        google_verifier: GoogleIdentityVerifier | None = None,
    ) -> None:
        self.user_repo = user_repo
        self.config = config
        self.google_verifier = google_verifier

    def issue_access_token(self, user_id: str, username: str | None = None) -> str:
        now = datetime.now(timezone.utc)
        payload = {
            "sub": user_id,
            "username": username,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(hours=24)).timestamp()),
        }
        return jwt.encode(payload, self.config.jwt_secret_key, algorithm="HS256")

    @staticmethod
    def normalize_email(email: str) -> str:
        return email.strip().lower()

    @staticmethod
    def normalize_provider_subject(provider_subject: str) -> str:
        return provider_subject.strip()

    @staticmethod
    def normalize_provider_name(provider: str) -> str:
        return provider.strip().lower()

    def build_frontend_auth_url(self, query_key: str, token: str) -> str | None:
        base_url = (
            self.config.frontend_url
            or self.config.public_url
            or self.config.render_external_url
            or ""
        ).rstrip("/")
        if not base_url:
            return None
        return f"{base_url}/login?{query_key}={token}"

    def build_auth_session(self, user_id: str, user: UserProfileView | None) -> AuthSessionDto:
        username = user.username if user else None
        return AuthSessionDto.create(
            access_token=self.issue_access_token(user_id, username),
            user_id=user_id,
            username=username,
            full_name=user.full_name if user else None,
        )

    async def _load_user_profile_view(self, user_id: str) -> UserProfileView | None:
        return await self.user_repo.get_user_by_id_view(user_id)

    async def _load_user_by_identity_view(self, provider: str, provider_id: str) -> UserProfileView | None:
        return await self.user_repo.get_user_by_identity_view(provider, provider_id)

    async def _load_user_by_email_view(self, email: str) -> UserProfileView | None:
        return await self.user_repo.get_user_by_email_view(email)

    async def _load_auth_methods_view(self, user_id: str) -> AuthMethodsView:
        return await self.user_repo.list_auth_methods_view(user_id)

    async def get_auth_methods(self, user_id: str) -> AuthMethodsDto:
        return AuthMethodsDto.from_view(await self._load_auth_methods_view(user_id))

    async def get_current_user(self, user_id: str) -> UserProfileDto:
        user = await self._load_user_profile_view(user_id)
        if not user:
            raise NotFoundError("User not found")
        return UserProfileDto.from_view(user)

    async def verify_google_id_token(self, id_token: str) -> GoogleIdentityClaims:
        token = id_token.strip()
        if not token:
            raise ValidationError("id_token is required")
        if self.google_verifier is None:
            raise UnauthorizedError("Google identity verifier is not configured")
        return await self.google_verifier.verify_id_token(token)

    async def email_register(self, email: str, password: str, full_name: str | None = None) -> AuthSessionDto:
        normalized_email = self.normalize_email(email)
        existing = await self._load_user_by_identity_view(AUTH_PROVIDER_EMAIL, normalized_email)
        if existing:
            raise ConflictError("Email is already linked to another account")

        user_id, _ = await self.user_repo.get_or_create_by_email(normalized_email, full_name)
        await self.user_repo.set_password(user_id, password)
        return self.build_auth_session(user_id, await self._load_user_profile_view(user_id))

    async def email_login(self, email: str, password: str) -> AuthSessionDto:
        normalized_email = self.normalize_email(email)
        user = await self._load_user_by_identity_view(AUTH_PROVIDER_EMAIL, normalized_email)
        if not user:
            user = await self._load_user_by_email_view(normalized_email)
        if not user:
            raise UnauthorizedError("Invalid email or password")
        if not await self.user_repo.verify_password(user.id, password):
            raise UnauthorizedError("Invalid email or password")
        return self.build_auth_session(user.id, user)

    async def link_email(self, current_user_id: str, email: str, password: str) -> AuthMethodsDto:
        normalized_email = self.normalize_email(email)
        existing = await self._load_user_by_identity_view(AUTH_PROVIDER_EMAIL, normalized_email)
        if existing and existing.id != current_user_id:
            raise ConflictError("Email is already linked to another account")

        await self.user_repo.link_email_auth(current_user_id, normalized_email, password)
        return await self.get_auth_methods(current_user_id)

    async def request_email_verification(self, current_user_id: str) -> AuthActionDto:
        user = await self._load_user_profile_view(current_user_id)
        if not user or not user.email:
            raise ValidationError("Email auth must be linked before requesting verification")
        if not await self.user_repo.has_auth_method(current_user_id, AUTH_PROVIDER_EMAIL):
            raise ValidationError("Email auth must be linked before requesting verification")

        token_data = cast(JsonObject, await self.user_repo.create_email_verification_token(current_user_id, user.email))
        token = str(token_data["token"])
        return AuthActionDto.create(
            status=AUTH_STATUS_VERIFICATION_REQUESTED,
            delivery=AUTH_DELIVERY_MANUAL_LINK,
            expires_at=str(token_data["expires_at"]),
            token=token,
            url=self.build_frontend_auth_url(EMAIL_VERIFICATION_QUERY_KEY, token),
        )

    async def confirm_email_verification(self, token: str) -> AuthMethodsDto:
        token_value = token.strip()
        if not token_value:
            raise ValidationError("token is required")

        payload = cast(JsonObject | None, await self.user_repo.consume_email_verification_token(token_value))
        if not payload:
            raise ValidationError("Invalid or expired email verification token")

        user_id = str(_payload_get(payload, "user_id"))
        email = str(_payload_get(payload, "email"))
        await self.user_repo.mark_email_verified(user_id, email)
        return AuthMethodsDto.from_view(await self._load_auth_methods_view(user_id), verified_email=email)

    async def google_login_with_id_token(self, id_token: str) -> AuthSessionDto:
        claims = await self.verify_google_id_token(id_token)
        if isinstance(claims, Mapping):
            claims = GoogleIdentityClaims(
                provider_subject=str(claims["provider_subject"]),
                email=cast(str | None, claims.get("email")),
                full_name=cast(str | None, claims.get("full_name")),
            )
        return await self.google_login(claims.provider_subject, claims.email, claims.full_name)

    async def link_google_with_id_token(self, current_user_id: str, id_token: str) -> AuthMethodsDto:
        claims = await self.verify_google_id_token(id_token)
        if isinstance(claims, Mapping):
            claims = GoogleIdentityClaims(
                provider_subject=str(claims["provider_subject"]),
                email=cast(str | None, claims.get("email")),
                full_name=cast(str | None, claims.get("full_name")),
            )
        return await self.link_google(current_user_id, claims.provider_subject, claims.email)

    async def google_login(
        self,
        provider_subject: str,
        email: str | None = None,
        full_name: str | None = None,
    ) -> AuthSessionDto:
        normalized_subject = self.normalize_provider_subject(provider_subject)
        if not normalized_subject:
            raise ValidationError("provider_subject is required")

        user = await self._load_user_by_identity_view(AUTH_PROVIDER_GOOGLE, normalized_subject)
        if user:
            return self.build_auth_session(user.id, user)

        normalized_email = self.normalize_email(email) if email else None
        if normalized_email:
            existing_email_user = await self._load_user_by_email_view(normalized_email)
            if existing_email_user:
                raise ConflictError(
                    "Google account email is already used by another account. Sign in and link Google from your profile"
                )

        user_id = await self.user_repo.create_user(full_name=full_name, email=normalized_email)
        await self.user_repo.link_identity(user_id, AUTH_PROVIDER_GOOGLE, normalized_subject)
        return self.build_auth_session(user_id, await self._load_user_profile_view(user_id))

    async def link_google(self, current_user_id: str, provider_subject: str, email: str | None = None) -> AuthMethodsDto:
        normalized_subject = self.normalize_provider_subject(provider_subject)
        if not normalized_subject:
            raise ValidationError("provider_subject is required")

        existing = await self._load_user_by_identity_view(AUTH_PROVIDER_GOOGLE, normalized_subject)
        if existing and existing.id != current_user_id:
            raise ConflictError("Google account is already linked to another account")

        try:
            await self.user_repo.link_identity(current_user_id, AUTH_PROVIDER_GOOGLE, normalized_subject)
        except ValueError:
            raise ConflictError("Google account is already linked to another account") from None

        normalized_email = self.normalize_email(email) if email else None
        if normalized_email:
            existing_email_user = await self._load_user_by_email_view(normalized_email)
            if existing_email_user and existing_email_user.id != current_user_id:
                raise ConflictError("Google account email is already used by another account")
            current_user = await self._load_user_profile_view(current_user_id)
            if current_user and not current_user.email:
                await self.user_repo.update_user(current_user_id, {"email": normalized_email})

        return await self.get_auth_methods(current_user_id)

    async def change_password(self, current_user_id: str, new_password: str, current_password: str | None = None) -> AuthMethodsDto:
        if not await self.user_repo.has_auth_method(current_user_id, AUTH_PROVIDER_EMAIL):
            raise ValidationError("Email auth must be linked before setting or changing a password")

        if await self.user_repo.has_password(current_user_id):
            if not current_password:
                raise ValidationError("current_password is required")
            if not await self.user_repo.verify_password(current_user_id, current_password):
                raise UnauthorizedError("Current password is incorrect")

        await self.user_repo.set_password(current_user_id, new_password)
        return await self.get_auth_methods(current_user_id)

    async def request_password_reset(self, email: str) -> AuthActionDto:
        normalized_email = self.normalize_email(email)
        user = await self._load_user_by_identity_view(AUTH_PROVIDER_EMAIL, normalized_email)
        if not user:
            user = await self._load_user_by_email_view(normalized_email)

        response = AuthActionDto.create(
            status=AUTH_STATUS_PASSWORD_RESET_REQUESTED,
            delivery=AUTH_DELIVERY_MANUAL_LINK,
        )
        if not user:
            return response
        if not await self.user_repo.has_auth_method(user.id, AUTH_PROVIDER_EMAIL):
            return response

        token_data = cast(JsonObject, await self.user_repo.create_password_reset_token(user.id))
        token = str(token_data["token"])
        return AuthActionDto.create(
            status=response.status,
            delivery=response.delivery,
            expires_at=str(token_data["expires_at"]),
            token=token,
            url=self.build_frontend_auth_url(PASSWORD_RESET_QUERY_KEY, token),
        )

    async def confirm_password_reset(self, token: str, new_password: str) -> AuthActionDto:
        token_value = token.strip()
        if not token_value:
            raise ValidationError("token is required")

        payload = cast(JsonObject | None, await self.user_repo.consume_password_reset_token(token_value))
        if not payload:
            raise ValidationError("Invalid or expired password reset token")

        user_id = str(_payload_get(payload, "user_id"))
        await self.user_repo.set_password(user_id, new_password)
        return AuthActionDto.create(status=AUTH_STATUS_PASSWORD_RESET_COMPLETED, user_id=user_id)

    async def unlink_auth_method(self, current_user_id: str, provider: str) -> AuthMethodsDto:
        normalized_provider = self.normalize_provider_name(provider)
        if normalized_provider not in ALLOWED_AUTH_PROVIDERS:
            raise ValidationError("Unsupported auth provider")

        if not await self.user_repo.has_auth_method(current_user_id, normalized_provider):
            raise NotFoundError("Auth method not found")

        if await self.user_repo.count_auth_methods(current_user_id) <= 1:
            raise ValidationError("Cannot unlink the last auth method")

        if normalized_provider == AUTH_PROVIDER_EMAIL and await self.user_repo.has_password(current_user_id):
            raise ValidationError("Remove or replace the password-based login path before unlinking email")

        await self.user_repo.unlink_identity(current_user_id, normalized_provider)
        return await self.get_auth_methods(current_user_id)
