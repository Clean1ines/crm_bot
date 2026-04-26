"""
Infrastructure resource lifecycle helpers.

Infrastructure owns low-level resources only:
- database pool creation/closing
- platform-owner bootstrap SQL

No src.agent.
No src.tools registry wiring.
No application composition.
"""

from typing import Any

import asyncpg


async def init_db(*, settings: Any, logger: Any) -> asyncpg.Pool:
    if not settings.DATABASE_URL:
        raise RuntimeError("DATABASE_URL not configured")

    logger.info(
        "Initializing database connection pool",
        extra={"url": settings.DATABASE_URL[:20] + "..."},
    )

    db_pool = await asyncpg.create_pool(
        settings.DATABASE_URL,
        min_size=settings.DB_POOL_MIN_SIZE,
        max_size=settings.DB_POOL_MAX_SIZE,
        command_timeout=settings.DB_COMMAND_TIMEOUT,
    )

    logger.info(
        "Database pool initialized",
        extra={
            "min_size": settings.DB_POOL_MIN_SIZE,
            "max_size": settings.DB_POOL_MAX_SIZE,
        },
    )
    return db_pool


async def shutdown_db(db_pool: asyncpg.Pool | None, *, logger: Any) -> None:
    if db_pool is None:
        return

    logger.info("Closing database connection pool")
    await db_pool.close()
    logger.info("Database pool closed")


def platform_owner_telegram_id(*, settings: Any) -> int | None:
    if not settings.BOOTSTRAP_PLATFORM_OWNER:
        return None

    configured_id = settings.PLATFORM_OWNER_TELEGRAM_ID or settings.ADMIN_CHAT_ID
    if not configured_id:
        return None

    return int(configured_id)


async def bootstrap_platform_owner(
    db_pool: asyncpg.Pool,
    *,
    settings: Any,
    logger: Any,
) -> str | None:
    telegram_id = platform_owner_telegram_id(settings=settings)
    if telegram_id is None:
        logger.info("Platform owner bootstrap skipped")
        return None

    async with db_pool.acquire() as conn:
        user_id = await conn.fetchval(
            """
            INSERT INTO users (telegram_id, full_name, is_platform_admin)
            VALUES ($1, $2, true)
            ON CONFLICT (telegram_id)
            DO UPDATE SET
                is_platform_admin = true,
                updated_at = NOW()
            RETURNING id
            """,
            telegram_id,
            "Platform Owner",
        )

        await conn.execute(
            """
            INSERT INTO auth_identities (user_id, provider, provider_id)
            VALUES ($1, 'telegram', $2)
            ON CONFLICT (provider, provider_id) DO NOTHING
            """,
            user_id,
            str(telegram_id),
        )

    logger.info(
        "Platform owner bootstrapped",
        extra={"user_id": str(user_id), "telegram_id": telegram_id},
    )
    return str(user_id)
