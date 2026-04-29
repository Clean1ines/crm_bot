"""
User Repository for managing platform users and authentication identities.

This module provides data access methods for users and auth_identities tables,
supporting multi-provider authentication and user management.
"""

import json
import asyncpg
import base64
import binascii
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from src.domain.display_names import join_name_parts, normalize_display_text
from src.domain.identity.auth_providers import (
    AUTH_PROVIDER_EMAIL,
    AUTH_PROVIDER_TELEGRAM,
)
from src.domain.identity.user_views import (
    AuthMethodView,
    AuthMethodsView,
    UserProfileView,
    EmailVerificationTokenView,
    PasswordResetTokenView,
    ConsumedEmailVerificationToken,
    ConsumedPasswordResetToken,
)
from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)

_UPDATABLE_USER_FIELDS = (
    "full_name",
    "email",
    "username",
    "telegram_id",
    "is_platform_admin",
    "user_metadata",
)


def _telegram_full_name(first_name: str, last_name: str | None) -> str | None:
    return join_name_parts(first_name, last_name)


async def _fill_missing_telegram_profile_fields(
    conn: asyncpg.Connection,
    *,
    user_id: str,
    username: str | None,
    full_name: str | None,
) -> None:
    await conn.execute(
        """
        UPDATE users
        SET
            username = COALESCE(NULLIF(users.username, ''), NULLIF($2, '')),
            full_name = COALESCE(NULLIF(users.full_name, ''), NULLIF($3, ''))
        WHERE id = $1
        """,
        user_id,
        normalize_display_text(username),
        normalize_display_text(full_name),
    )


def _safe_metadata_dict(value) -> dict:
    """
    Normalize users.user_metadata from asyncpg/jsonb/string/None into dict.

    Production can return this as a JSON string after older writes, and
    dict("{}") crashes with:
    ValueError: dictionary update sequence element #0 has length 1; 2 is required
    """
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return {}
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    if hasattr(value, "items"):
        return dict(value)
    return {}


def _hash_password(
    password: str, salt: bytes | None = None, iterations: int = 210_000
) -> str:
    """
    Hash a password using PBKDF2-SHA256 with an encoded random salt.

    This keeps the project self-contained until a dedicated password
    hashing dependency is introduced.
    """
    salt = salt or secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return "pbkdf2_sha256${}${}${}".format(
        iterations,
        base64.b64encode(salt).decode("ascii"),
        base64.b64encode(derived).decode("ascii"),
    )


def _verify_password(password: str, stored_hash: str) -> bool:
    try:
        algo, iterations_s, salt_b64, hash_b64 = stored_hash.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        iterations = int(iterations_s)
        salt = base64.b64decode(salt_b64.encode("ascii"))
        expected = base64.b64decode(hash_b64.encode("ascii"))
        derived = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt, iterations
        )
        return secrets.compare_digest(derived, expected)
    except (ValueError, UnicodeEncodeError, binascii.Error):
        return False


class UserRepository:
    """
    Repository for managing user accounts and authentication identities.

    Supports creating users, linking identities, and retrieving users
    by various identifiers (telegram, email, etc.).

    Attributes:
        pool: Asyncpg connection pool for database operations.
    """

    def __init__(self, pool: asyncpg.Pool) -> None:
        """
        Initialize the UserRepository with a database connection pool.

        Args:
            pool: Asyncpg connection pool for database operations.
        """
        self.pool = pool
        logger.debug("UserRepository initialized")

    async def get_or_create_by_telegram(
        self,
        telegram_id: int,
        first_name: str,
        username: str | None = None,
        last_name: str | None = None,
    ) -> tuple[str, bool]:
        """
        Get or create a user by Telegram ID.

        If the user already exists (by auth_identity or users.telegram_id),
        returns the existing user ID. Otherwise, creates a new user and
        adds a Telegram identity.

        Args:
            telegram_id: Telegram chat ID.
            first_name: User's first name from Telegram.
            username: Telegram username (optional).

        Returns:
            Tuple of (user_id (str), created (bool)).
        """
        logger.info(
            "Getting or creating user by telegram", extra={"telegram_id": telegram_id}
        )

        full_name = _telegram_full_name(first_name, last_name)

        async with self.pool.acquire() as conn:
            # Try to find existing identity
            row = await conn.fetchrow(
                """
                SELECT user_id
                FROM auth_identities
                WHERE provider = 'telegram' AND provider_id = $1
            """,
                str(telegram_id),
            )

            if row:
                user_id = str(row["user_id"])
                await _fill_missing_telegram_profile_fields(
                    conn,
                    user_id=user_id,
                    username=username,
                    full_name=full_name,
                )
                logger.debug(
                    "Existing user found via identity", extra={"user_id": user_id}
                )
                return user_id, False

            # Check legacy users table (telegram_id column)
            row = await conn.fetchrow(
                """
                SELECT id FROM users WHERE telegram_id = $1
            """,
                telegram_id,
            )

            if row:
                user_id = str(row["id"])
                # Migrate to new identity system
                await conn.execute(
                    """
                    INSERT INTO auth_identities (user_id, provider, provider_id)
                    VALUES ($1, 'telegram', $2)
                    ON CONFLICT (provider, provider_id) DO NOTHING
                """,
                    user_id,
                    str(telegram_id),
                )
                await _fill_missing_telegram_profile_fields(
                    conn,
                    user_id=user_id,
                    username=username,
                    full_name=full_name,
                )
                logger.info(
                    "Migrated legacy user to auth_identities",
                    extra={"user_id": user_id},
                )
                return user_id, False

            # Create new user
            user_id = await conn.fetchval(
                """
                INSERT INTO users (id, telegram_id, username, full_name)
                VALUES (gen_random_uuid(), $1, $2, $3)
                RETURNING id
            """,
                telegram_id,
                username,
                full_name,
            )
            user_id = str(user_id)

            # Create identity
            await conn.execute(
                """
                INSERT INTO auth_identities (user_id, provider, provider_id)
                VALUES ($1, 'telegram', $2)
            """,
                user_id,
                str(telegram_id),
            )

            logger.info(
                "New user created",
                extra={"user_id": user_id, "telegram_id": telegram_id},
            )
            return user_id, True

    async def get_or_create_by_email(
        self, email: str, full_name: str | None = None
    ) -> tuple[str, bool]:
        """
        Get or create a user by canonical email identity.
        """
        normalized_email = email.strip().lower()

        existing = await self.get_user_by_identity_view("email", normalized_email)
        if existing:
            return str(existing.id), False

        legacy_user = await self.get_user_by_email_view(normalized_email)
        if legacy_user:
            await self.link_identity(str(legacy_user.id), "email", normalized_email)
            if not legacy_user.email:
                async with self.pool.acquire() as conn:
                    await conn.execute(
                        "UPDATE users SET email = $1 WHERE id = $2",
                        normalized_email,
                        legacy_user.id,
                    )
            return str(legacy_user.id), False

        async with self.pool.acquire() as conn:
            user_id = await conn.fetchval(
                """
                INSERT INTO users (id, email, full_name)
                VALUES (gen_random_uuid(), $1, $2)
                RETURNING id
            """,
                normalized_email,
                full_name,
            )
            user_id = str(user_id)
            await conn.execute(
                """
                INSERT INTO auth_identities (user_id, provider, provider_id)
                VALUES ($1, 'email', $2)
            """,
                user_id,
                normalized_email,
            )
            logger.info(
                "New email user created",
                extra={"user_id": user_id, "email": normalized_email},
            )
            return user_id, True

    async def create_user(
        self,
        full_name: str | None = None,
        email: str | None = None,
        username: str | None = None,
    ) -> str:
        """
        Create a new platform user without implicitly linking auth providers.

        This is used for providers like Google where we intentionally avoid
        auto-merging accounts by email.
        """
        normalized_email = email.strip().lower() if email else None
        async with self.pool.acquire() as conn:
            user_id = await conn.fetchval(
                """
                INSERT INTO users (id, email, username, full_name)
                VALUES (gen_random_uuid(), $1, $2, $3)
                RETURNING id
            """,
                normalized_email,
                username,
                full_name,
            )
            return str(user_id)

    async def add_identity(self, user_id: str, provider: str, provider_id: str) -> None:
        """
        Add an authentication identity for an existing user.

        Args:
            user_id: UUID of the user.
            provider: Provider name (e.g., 'telegram', 'email', 'google').
            provider_id: Unique identifier from the provider.
        """
        await self.link_identity(user_id, provider, provider_id)

    async def link_identity(
        self, user_id: str, provider: str, provider_id: str
    ) -> bool:
        """
        Link an auth identity to an existing user.

        Returns:
            True if a new identity row was inserted, False if it already existed
            for the same user.
        """
        logger.info(
            "Adding identity",
            extra={
                "user_id": user_id,
                "provider": provider,
                "provider_id": provider_id,
            },
        )
        async with self.pool.acquire() as conn:
            existing = await conn.fetchrow(
                """
                SELECT user_id
                FROM auth_identities
                WHERE provider = $1 AND provider_id = $2
            """,
                provider,
                provider_id,
            )
            if existing:
                if str(existing["user_id"]) != str(user_id):
                    raise ValueError(
                        f"Auth identity {provider}:{provider_id} is already linked to another user"
                    )
                return False
            await conn.execute(
                """
                INSERT INTO auth_identities (user_id, provider, provider_id)
                VALUES ($1, $2, $3)
            """,
                user_id,
                provider,
                provider_id,
            )
        return True

    async def get_user_by_identity_view(
        self, provider: str, provider_id: str
    ) -> UserProfileView | None:
        """
        Retrieve a user by external auth identity.
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT u.*
                FROM users u
                JOIN auth_identities ai ON ai.user_id = u.id
                WHERE ai.provider = $1 AND ai.provider_id = $2
            """,
                provider,
                provider_id,
            )
            if not row:
                return None
            return UserProfileView.from_record(dict(row))

    async def get_user_by_telegram_view(
        self, telegram_id: int
    ) -> UserProfileView | None:
        """
        Retrieve a user by Telegram ID using auth_identities.

        Args:
            telegram_id: Telegram chat ID.

        Returns:
            User record as dict, or None if not found.
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT u.*
                FROM users u
                JOIN auth_identities ai ON ai.user_id = u.id
                WHERE ai.provider = 'telegram' AND ai.provider_id = $1
            """,
                str(telegram_id),
            )

            if not row:
                return None

            return UserProfileView.from_record(dict(row))

    async def get_user_by_id_view(self, user_id: str) -> UserProfileView | None:
        """
        Retrieve a user by UUID.

        Args:
            user_id: User UUID (string).

        Returns:
            User record as dict, or None if not found.
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM users WHERE id = $1", user_id)
            if not row:
                return None
            return UserProfileView.from_record(dict(row))

    async def is_platform_admin(self, user_id: str) -> bool:
        """
        Return whether a platform user has global platform administration rights.
        """
        async with self.pool.acquire() as conn:
            value = await conn.fetchval(
                "SELECT is_platform_admin FROM users WHERE id = $1",
                user_id,
            )
            return bool(value)

    async def get_user_by_email_view(self, email: str) -> UserProfileView | None:
        """
        Retrieve a user by email address.

        Args:
            email: User's email address.

        Returns:
            User record as dict, or None if not found.
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM users WHERE email = $1", email)
            if not row:
                row = await conn.fetchrow(
                    """
                    SELECT u.*
                    FROM users u
                    JOIN auth_identities ai ON ai.user_id = u.id
                    WHERE ai.provider = 'email' AND ai.provider_id = $1
            """,
                    email,
                )
            if not row:
                return None
            return UserProfileView.from_record(dict(row))

    async def list_auth_methods_view(self, user_id: str) -> AuthMethodsView:
        """
        Return all auth methods linked to a user and whether a local password is set.
        """
        async with self.pool.acquire() as conn:
            user_row = await conn.fetchrow(
                """
                SELECT email, user_metadata
                FROM users
                WHERE id = $1
            """,
                user_id,
            )
            identity_rows = await conn.fetch(
                """
                SELECT provider, provider_id, created_at
                FROM auth_identities
                WHERE user_id = $1
                ORDER BY created_at ASC
            """,
                user_id,
            )
            has_password = await conn.fetchval(
                """
                SELECT 1 FROM user_credentials WHERE user_id = $1
            """,
                user_id,
            )

            methods: list[AuthMethodView] = []
            metadata = _safe_metadata_dict(
                user_row["user_metadata"] if user_row else None
            )
            verified_email = (
                str(metadata.get("email_verified_address") or "").strip().lower()
            )
            verified_at = metadata.get("email_verified_at")
            for row in identity_rows:
                verified = None
                verified_at_value = None
                if row["provider"] == AUTH_PROVIDER_EMAIL:
                    provider_email = str(row["provider_id"]).strip().lower()
                    verified = bool(verified_email and provider_email == verified_email)
                    verified_at_value = verified_at if verified else None
                method = AuthMethodView(
                    provider=row["provider"],
                    provider_id=row["provider_id"],
                    created_at=row["created_at"].isoformat()
                    if row["created_at"]
                    else None,
                    verified=verified,
                    verified_at=verified_at_value,
                )
                methods.append(method)

            return AuthMethodsView(
                user_id=user_id,
                methods=methods,
                has_password=bool(has_password),
                verified_email=verified_email or None,
            )

    async def count_auth_methods(self, user_id: str) -> int:
        """
        Return the number of auth identities currently linked to a user.
        """
        async with self.pool.acquire() as conn:
            value = await conn.fetchval(
                """
                SELECT COUNT(*)
                FROM auth_identities
                WHERE user_id = $1
            """,
                user_id,
            )
            return int(value or 0)

    async def has_auth_method(self, user_id: str, provider: str) -> bool:
        """
        Return whether the user has an auth identity for the given provider.
        """
        async with self.pool.acquire() as conn:
            value = await conn.fetchval(
                """
                SELECT 1
                FROM auth_identities
                WHERE user_id = $1 AND provider = $2
                LIMIT 1
            """,
                user_id,
                provider,
            )
            return bool(value)

    async def set_password(self, user_id: str, password: str) -> None:
        """
        Create or update a local password credential for a user.
        """
        password_hash = _hash_password(password)
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO user_credentials (user_id, password_hash, password_updated_at)
                VALUES ($1, $2, NOW())
                ON CONFLICT (user_id)
                DO UPDATE SET password_hash = EXCLUDED.password_hash,
                              password_updated_at = NOW()
            """,
                user_id,
                password_hash,
            )

    async def link_email_auth(self, user_id: str, email: str, password: str) -> None:
        """
        Link an email identity to an existing user and set a local password.
        """
        normalized_email = email.strip().lower()
        await self.link_identity(user_id, "email", normalized_email)
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT user_metadata FROM users WHERE id = $1", user_id
            )
            metadata = _safe_metadata_dict(row["user_metadata"] if row else None)
            metadata.pop("email_verified_at", None)
            metadata.pop("email_verified_address", None)
            await conn.execute(
                "UPDATE users SET email = $1, user_metadata = $2, updated_at = NOW() WHERE id = $3",
                normalized_email,
                metadata,
                user_id,
            )
        await self.set_password(user_id, password)

    async def verify_password(self, user_id: str, password: str) -> bool:
        """
        Validate a local password credential for a user.
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT password_hash
                FROM user_credentials
                WHERE user_id = $1
            """,
                user_id,
            )
            if not row:
                return False
            return _verify_password(password, row["password_hash"])

    async def has_password(self, user_id: str) -> bool:
        """
        Return whether the user currently has a local password credential.
        """
        async with self.pool.acquire() as conn:
            value = await conn.fetchval(
                """
                SELECT 1
                FROM user_credentials
                WHERE user_id = $1
                LIMIT 1
            """,
                user_id,
            )
            return bool(value)

    async def unlink_identity(self, user_id: str, provider: str) -> bool:
        """
        Remove an auth identity from a user.

        Returns:
            True when an identity row was removed, False when nothing matched.
        """
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                deleted = await conn.fetchval(
                    """
                    DELETE FROM auth_identities
                    WHERE user_id = $1 AND provider = $2
                    RETURNING provider
                """,
                    user_id,
                    provider,
                )
                if not deleted:
                    return False

                if provider == AUTH_PROVIDER_EMAIL:
                    row = await conn.fetchrow(
                        "SELECT user_metadata FROM users WHERE id = $1", user_id
                    )
                    metadata = _safe_metadata_dict(
                        row["user_metadata"] if row else None
                    )
                    metadata.pop("email_verified_at", None)
                    metadata.pop("email_verified_address", None)
                    await conn.execute(
                        """
                        UPDATE users
                        SET email = NULL, user_metadata = $2, updated_at = NOW()
                        WHERE id = $1
                    """,
                        user_id,
                        metadata,
                    )

                if provider == AUTH_PROVIDER_TELEGRAM:
                    await conn.execute(
                        """
                        UPDATE users
                        SET telegram_id = NULL, updated_at = NOW()
                        WHERE id = $1
                    """,
                        user_id,
                    )

                return True

    async def update_user(self, user_id: str, data: dict[str, object]) -> bool:
        """
        Update user fields.

        Args:
            user_id: User UUID.
            data: Dictionary of fields to update (e.g., {'full_name': 'New Name'}).

        Returns:
            True if updated, False if user not found.
        """
        if not data:
            return True

        invalid_fields = sorted(set(data) - set(_UPDATABLE_USER_FIELDS))
        if invalid_fields:
            raise ValueError(
                f"Unsupported user update fields: {', '.join(invalid_fields)}"
            )

        query = """
            UPDATE users
            SET
                full_name = CASE WHEN $2 THEN $3 ELSE full_name END,
                email = CASE WHEN $4 THEN $5 ELSE email END,
                username = CASE WHEN $6 THEN $7 ELSE username END,
                telegram_id = CASE WHEN $8 THEN $9 ELSE telegram_id END,
                is_platform_admin = CASE WHEN $10 THEN $11 ELSE is_platform_admin END,
                user_metadata = CASE WHEN $12 THEN $13 ELSE user_metadata END,
                updated_at = NOW()
            WHERE id = $1
        """
        params: list[object] = [
            user_id,
            "full_name" in data,
            data.get("full_name"),
            "email" in data,
            data.get("email"),
            "username" in data,
            data.get("username"),
            "telegram_id" in data,
            data.get("telegram_id"),
            "is_platform_admin" in data,
            data.get("is_platform_admin"),
            "user_metadata" in data,
            data.get("user_metadata"),
        ]

        async with self.pool.acquire() as conn:
            result = await conn.execute(query, *params)
            return result == "UPDATE 1"

    async def create_email_verification_token(
        self,
        user_id: str,
        email: str,
        ttl_hours: int = 24,
    ) -> EmailVerificationTokenView:
        """
        Create a one-time email verification token for a linked email identity.
        """
        normalized_email = email.strip().lower()
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=ttl_hours)

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    UPDATE email_verification_tokens
                    SET used_at = NOW()
                    WHERE user_id = $1 AND email = $2 AND used_at IS NULL
                """,
                    user_id,
                    normalized_email,
                )
                await conn.execute(
                    """
                    INSERT INTO email_verification_tokens (user_id, email, token, expires_at)
                    VALUES ($1, $2, $3, $4)
                """,
                    user_id,
                    normalized_email,
                    token,
                    expires_at,
                )

        return EmailVerificationTokenView(
            token=token, expires_at=expires_at.isoformat()
        )

    async def consume_email_verification_token(
        self, token: str
    ) -> ConsumedEmailVerificationToken | None:
        """
        Mark an email verification token as used and return its payload when valid.
        """
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    SELECT user_id, email
                    FROM email_verification_tokens
                    WHERE token = $1
                      AND used_at IS NULL
                      AND expires_at > NOW()
                    FOR UPDATE
                """,
                    token,
                )
                if not row:
                    return None
                await conn.execute(
                    """
                    UPDATE email_verification_tokens
                    SET used_at = NOW()
                    WHERE token = $1
                """,
                    token,
                )
                return ConsumedEmailVerificationToken(
                    user_id=str(row["user_id"]), email=row["email"]
                )

    async def mark_email_verified(self, user_id: str, email: str) -> None:
        """
        Persist verified email metadata on the platform user profile.
        """
        normalized_email = email.strip().lower()
        verified_at = datetime.now(timezone.utc).isoformat()
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT user_metadata FROM users WHERE id = $1", user_id
            )
            metadata = _safe_metadata_dict(row["user_metadata"] if row else None)
            metadata["email_verified_address"] = normalized_email
            metadata["email_verified_at"] = verified_at
            await conn.execute(
                """
                UPDATE users
                SET user_metadata = $2, updated_at = NOW()
                WHERE id = $1
            """,
                user_id,
                metadata,
            )

    async def create_password_reset_token(
        self,
        user_id: str,
        ttl_hours: int = 2,
    ) -> PasswordResetTokenView:
        """
        Create a one-time password reset token for a platform user.
        """
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=ttl_hours)

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    UPDATE password_reset_tokens
                    SET used_at = NOW()
                    WHERE user_id = $1 AND used_at IS NULL
                """,
                    user_id,
                )
                await conn.execute(
                    """
                    INSERT INTO password_reset_tokens (user_id, token, expires_at)
                    VALUES ($1, $2, $3)
                """,
                    user_id,
                    token,
                    expires_at,
                )

        return PasswordResetTokenView(token=token, expires_at=expires_at.isoformat())

    async def consume_password_reset_token(
        self, token: str
    ) -> ConsumedPasswordResetToken | None:
        """
        Mark a password reset token as used and return its payload when valid.
        """
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    SELECT user_id
                    FROM password_reset_tokens
                    WHERE token = $1
                      AND used_at IS NULL
                      AND expires_at > NOW()
                    FOR UPDATE
                """,
                    token,
                )
                if not row:
                    return None
                await conn.execute(
                    """
                    UPDATE password_reset_tokens
                    SET used_at = NOW()
                    WHERE token = $1
                """,
                    token,
                )
                return ConsumedPasswordResetToken(user_id=str(row["user_id"]))
