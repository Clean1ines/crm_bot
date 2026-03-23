"""
User Repository for managing platform users and authentication identities.

This module provides data access methods for users and auth_identities tables,
supporting multi-provider authentication and user management.
"""

import uuid
import json
import asyncpg
from typing import Optional, Dict, Any, Tuple

from src.core.logging import get_logger
from src.core.config import settings

logger = get_logger(__name__)


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
        username: Optional[str] = None
    ) -> Tuple[str, bool]:
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
            "Getting or creating user by telegram",
            extra={"telegram_id": telegram_id}
        )
        
        async with self.pool.acquire() as conn:
            # Try to find existing identity
            row = await conn.fetchrow("""
                SELECT user_id
                FROM auth_identities
                WHERE provider = 'telegram' AND provider_id = $1
            """, str(telegram_id))
            
            if row:
                user_id = str(row['user_id'])
                logger.debug("Existing user found via identity", extra={"user_id": user_id})
                return user_id, False
            
            # Check legacy users table (telegram_id column)
            row = await conn.fetchrow("""
                SELECT id FROM users WHERE telegram_id = $1
            """, telegram_id)
            
            if row:
                user_id = str(row['id'])
                # Migrate to new identity system
                await conn.execute("""
                    INSERT INTO auth_identities (user_id, provider, provider_id)
                    VALUES ($1, 'telegram', $2)
                    ON CONFLICT (provider, provider_id) DO NOTHING
                """, user_id, str(telegram_id))
                logger.info("Migrated legacy user to auth_identities", extra={"user_id": user_id})
                return user_id, False
            
            # Create new user
            full_name = first_name
            # Optionally append last_name if available, but we don't have it here
            user_id = await conn.fetchval("""
                INSERT INTO users (id, telegram_id, username, full_name)
                VALUES (gen_random_uuid(), $1, $2, $3)
                RETURNING id
            """, telegram_id, username, full_name)
            user_id = str(user_id)
            
            # Create identity
            await conn.execute("""
                INSERT INTO auth_identities (user_id, provider, provider_id)
                VALUES ($1, 'telegram', $2)
            """, user_id, str(telegram_id))
            
            logger.info("New user created", extra={"user_id": user_id, "telegram_id": telegram_id})
            return user_id, True

    async def add_identity(
        self,
        user_id: str,
        provider: str,
        provider_id: str
    ) -> None:
        """
        Add an authentication identity for an existing user.
        
        Args:
            user_id: UUID of the user.
            provider: Provider name (e.g., 'telegram', 'email', 'google').
            provider_id: Unique identifier from the provider.
        """
        logger.info(
            "Adding identity",
            extra={"user_id": user_id, "provider": provider, "provider_id": provider_id}
        )
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO auth_identities (user_id, provider, provider_id)
                VALUES ($1, $2, $3)
                ON CONFLICT (provider, provider_id) DO NOTHING
            """, user_id, provider, provider_id)

    async def get_user_by_telegram(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        """
        Retrieve a user by Telegram ID using auth_identities.
        
        Args:
            telegram_id: Telegram chat ID.
        
        Returns:
            User record as dict, or None if not found.
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT u.*
                FROM users u
                JOIN auth_identities ai ON ai.user_id = u.id
                WHERE ai.provider = 'telegram' AND ai.provider_id = $1
            """, str(telegram_id))
            
            if not row:
                return None
            
            return dict(row)

    async def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
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
            return dict(row)

    async def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
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
                return None
            return dict(row)

    async def update_user(self, user_id: str, data: Dict[str, Any]) -> bool:
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
        
        sets = []
        params = [user_id]
        for idx, (key, value) in enumerate(data.items(), start=2):
            sets.append(f"{key} = ${idx}")
            params.append(value)
        
        query = f"""
            UPDATE users
            SET {', '.join(sets)}, updated_at = NOW()
            WHERE id = $1
        """
        
        async with self.pool.acquire() as conn:
            result = await conn.execute(query, *params)
            return result == "UPDATE 1"
