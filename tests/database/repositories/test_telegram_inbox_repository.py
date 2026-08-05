from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest

from src.domain.telegram_inbox import (
    TelegramInboxStatus,
    TelegramUpdateIdentity,
    TelegramUpdateSurface,
)
from src.infrastructure.config.settings import settings
from src.infrastructure.db.repositories.telegram_inbox_repository import (
    PostgresTelegramInboxRepository,
)


MIGRATION = Path("migrations/132_create_telegram_inbox.sql")


@pytest.fixture
async def migrated_pool():
    pool = await asyncpg.create_pool(settings.DATABASE_URL, min_size=1, max_size=10)
    migration_sql = MIGRATION.read_text(encoding="utf-8")
    async with pool.acquire() as conn:
        await _ensure_base_projects_schema(conn)
        await conn.execute(migration_sql)
        await conn.execute("TRUNCATE public.telegram_inbox_updates")
    yield pool
    await pool.close()


@pytest.fixture
async def project_id(migrated_pool) -> str:
    async with migrated_pool.acquire() as conn:
        project_id = await conn.fetchval(
            "INSERT INTO projects (name) VALUES ($1) RETURNING id",
            f"S1.1 project {uuid4()}",
        )
    return str(project_id)


@pytest.fixture
def repo(migrated_pool) -> PostgresTelegramInboxRepository:
    return PostgresTelegramInboxRepository(migrated_pool)


def _now(offset: int = 0) -> datetime:
    return datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc) + timedelta(seconds=offset)


def _identity(
    project_id: str,
    *,
    surface: TelegramUpdateSurface = TelegramUpdateSurface.CLIENT,
    bot_id: int = 1001,
    update_id: int = 42,
) -> TelegramUpdateIdentity:
    return TelegramUpdateIdentity.for_project_bot(
        surface=surface,
        project_id=project_id,
        telegram_bot_id=bot_id,
        telegram_update_id=update_id,
    )


def _platform_identity(
    *, bot_id: int = 9001, update_id: int = 7
) -> TelegramUpdateIdentity:
    return TelegramUpdateIdentity.for_platform_bot(
        platform_scope="platform_admin",
        telegram_bot_id=bot_id,
        telegram_update_id=update_id,
    )


async def _insert(
    repo: PostgresTelegramInboxRepository,
    identity: TelegramUpdateIdentity,
    *,
    text: str = "hello",
):
    return await repo.insert_or_read_existing(
        identity=identity,
        payload={"update_id": identity.telegram_update_id, "message": {"text": text}},
        received_at=_now(),
    )


async def _db_now(pool) -> datetime:
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT clock_timestamp()")


async def _db_time(pool, *, seconds: int = 0) -> datetime:
    return (await _db_now(pool)) + timedelta(seconds=seconds)


async def _force_lease_expiry(pool, inbox_id: str, *, seconds_ago: int = 30) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE public.telegram_inbox_updates
            SET lease_expires_at = clock_timestamp() - ($2::int * interval '1 second')
            WHERE id = $1
            """,
            inbox_id,
            seconds_ago,
        )


async def test_migration_is_clean_rerunnable_and_legacy_bot_ids_are_nullable(
    migrated_pool,
) -> None:
    migration_sql = MIGRATION.read_text(encoding="utf-8")

    async with migrated_pool.acquire() as conn:
        project_id = await conn.fetchval(
            "INSERT INTO projects (name) VALUES ($1) RETURNING id",
            f"S1.1 legacy {uuid4()}",
        )
        await conn.execute(migration_sql)
        await conn.execute(migration_sql)
        row = await conn.fetchrow(
            """
            SELECT client_telegram_bot_id, manager_telegram_bot_id
            FROM projects
            WHERE id = $1
            """,
            project_id,
        )
        table_exists = await conn.fetchval(
            "SELECT to_regclass('public.telegram_inbox_updates') IS NOT NULL"
        )

    assert row["client_telegram_bot_id"] is None
    assert row["manager_telegram_bot_id"] is None
    assert table_exists is True


async def test_migration_forward_fixes_missing_indexes_and_constraints(
    migrated_pool,
) -> None:
    migration_sql = MIGRATION.read_text(encoding="utf-8")

    async with migrated_pool.acquire() as conn:
        await conn.execute(
            "DROP INDEX IF EXISTS public.uq_telegram_inbox_project_update_identity"
        )
        await conn.execute(
            "ALTER TABLE public.telegram_inbox_updates "
            "DROP CONSTRAINT IF EXISTS ck_telegram_inbox_scope"
        )
        await conn.execute(migration_sql)
        project_index = await conn.fetchval(
            "SELECT to_regclass('public.uq_telegram_inbox_project_update_identity') IS NOT NULL"
        )
        scope_constraint = await conn.fetchval(
            """
            SELECT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'ck_telegram_inbox_scope'
            )
            """
        )

    assert project_index is True
    assert scope_constraint is True


async def test_processing_rows_require_ownership_fields(
    migrated_pool,
    project_id: str,
) -> None:
    async with migrated_pool.acquire() as conn:
        with pytest.raises(asyncpg.CheckViolationError):
            await conn.execute(
                """
                INSERT INTO public.telegram_inbox_updates (
                    surface,
                    project_id,
                    telegram_bot_id,
                    telegram_update_id,
                    original_payload,
                    original_payload_hash,
                    status
                )
                VALUES ('client', $1, 1001, 980, '{}'::jsonb, 'hash', 'processing')
                """,
                project_id,
            )

        row_id = await conn.fetchval(
            """
            INSERT INTO public.telegram_inbox_updates (
                surface,
                project_id,
                telegram_bot_id,
                telegram_update_id,
                original_payload,
                original_payload_hash
            )
            VALUES ('client', $1, 1001, 981, '{}'::jsonb, 'hash')
            RETURNING id
            """,
            project_id,
        )
        with pytest.raises(asyncpg.CheckViolationError):
            await conn.execute(
                """
                UPDATE public.telegram_inbox_updates
                SET status = 'processing'
                WHERE id = $1
                """,
                row_id,
            )


async def test_non_processing_rows_reject_active_ownership_fields(
    migrated_pool,
    project_id: str,
) -> None:
    async with migrated_pool.acquire() as conn:
        with pytest.raises(asyncpg.CheckViolationError):
            await conn.execute(
                """
                INSERT INTO public.telegram_inbox_updates (
                    surface,
                    project_id,
                    telegram_bot_id,
                    telegram_update_id,
                    original_payload,
                    original_payload_hash,
                    status,
                    owned_by,
                    owner_token,
                    lease_expires_at
                )
                VALUES (
                    'client',
                    $1,
                    1001,
                    982,
                    '{}'::jsonb,
                    'hash',
                    'received',
                    'worker-a',
                    'lease-a',
                    clock_timestamp() + interval '1 minute'
                )
                """,
                project_id,
            )

        row_id = await conn.fetchval(
            """
            INSERT INTO public.telegram_inbox_updates (
                surface,
                project_id,
                telegram_bot_id,
                telegram_update_id,
                original_payload,
                original_payload_hash
            )
            VALUES ('client', $1, 1001, 983, '{}'::jsonb, 'hash')
            RETURNING id
            """,
            project_id,
        )
        with pytest.raises(asyncpg.CheckViolationError):
            await conn.execute(
                """
                UPDATE public.telegram_inbox_updates
                SET
                    owned_by = 'worker-a',
                    owner_token = 'lease-a',
                    lease_expires_at = clock_timestamp() + interval '1 minute'
                WHERE id = $1
                """,
                row_id,
            )


async def test_atomic_concurrent_insert_creates_one_logical_update(
    repo: PostgresTelegramInboxRepository,
    project_id: str,
) -> None:
    identity = _identity(project_id)

    results = await asyncio.gather(
        _insert(repo, identity, text="one"),
        _insert(repo, identity, text="one"),
    )

    assert sum(1 for result in results if result.created) == 1
    assert {result.record.id for result in results} == {results[0].record.id}
    assert results[0].record.attempt_count == 0
    reread = await repo.get_by_identity(identity)
    assert reread is not None
    assert reread.duplicate_count == 1


async def test_bot_replacement_reused_update_id_is_distinct(
    repo: PostgresTelegramInboxRepository,
    project_id: str,
) -> None:
    old_bot = _identity(project_id, bot_id=1001, update_id=10)
    new_bot = _identity(project_id, bot_id=2002, update_id=10)

    old_result = await _insert(repo, old_bot, text="old")
    new_result = await _insert(repo, new_bot, text="new")
    duplicate_new = await _insert(repo, new_bot, text="new")

    assert old_result.record.id != new_result.record.id
    assert new_result.created is True
    assert duplicate_new.created is False
    assert duplicate_new.record.id == new_result.record.id


async def test_platform_identity_uses_numeric_bot_id_scope(
    repo: PostgresTelegramInboxRepository,
) -> None:
    first = await _insert(repo, _platform_identity(bot_id=9001, update_id=50))
    replacement = await _insert(repo, _platform_identity(bot_id=9002, update_id=50))
    duplicate = await _insert(repo, _platform_identity(bot_id=9002, update_id=50))

    assert first.record.id != replacement.record.id
    assert duplicate.record.id == replacement.record.id


async def test_duplicate_completed_preserves_lifecycle(
    repo: PostgresTelegramInboxRepository,
    project_id: str,
) -> None:
    inserted = await _insert(repo, _identity(project_id), text="done")
    claimed = await repo.claim_next(
        owner_id="worker-a",
        owner_token="lease-a",
        lease_expires_at=await _db_time(repo.pool, seconds=60),
    )
    assert claimed is not None
    assert await repo.complete(claimed.id, owner_token="lease-a")

    duplicate = await _insert(repo, _identity(project_id), text="done")

    assert duplicate.created is False
    assert duplicate.record.id == inserted.record.id
    assert duplicate.record.status is TelegramInboxStatus.COMPLETED
    assert duplicate.record.owner_token is None
    assert duplicate.record.attempt_count == 1


async def test_duplicate_processing_preserves_owner_and_lease(
    repo: PostgresTelegramInboxRepository,
    project_id: str,
) -> None:
    await _insert(repo, _identity(project_id), text="processing")
    lease_expires_at = await _db_time(repo.pool, seconds=60)
    claimed = await repo.claim_next(
        owner_id="worker-a",
        owner_token="lease-a",
        lease_expires_at=lease_expires_at,
    )
    assert claimed is not None

    duplicate = await _insert(repo, _identity(project_id), text="processing")

    assert duplicate.record.status is TelegramInboxStatus.PROCESSING
    assert duplicate.record.owner_token == "lease-a"
    assert duplicate.record.owned_by == "worker-a"
    assert duplicate.record.lease_expires_at == lease_expires_at
    assert duplicate.record.attempt_count == 1


async def test_duplicate_failed_preserves_attempts_and_error(
    repo: PostgresTelegramInboxRepository,
    project_id: str,
) -> None:
    await _insert(repo, _identity(project_id), text="retry")
    claimed = await repo.claim_next(
        owner_id="worker-a",
        owner_token="lease-a",
        lease_expires_at=await _db_time(repo.pool, seconds=60),
    )
    assert claimed is not None
    assert await repo.mark_retryable_failure(
        claimed.id,
        owner_token="lease-a",
        error_kind="telegram_timeout",
        error_message="provider timed out",
        next_attempt_at=_now(120),
    )

    duplicate = await _insert(repo, _identity(project_id), text="retry")

    assert duplicate.record.status is TelegramInboxStatus.RETRYABLE_FAILED
    assert duplicate.record.attempt_count == 1
    assert duplicate.record.last_error_kind == "telegram_timeout"
    assert duplicate.record.last_error_message == "provider timed out"
    assert duplicate.record.next_attempt_at == _now(120)


async def test_duplicate_terminal_failed_preserves_lifecycle_error_and_attempts(
    repo: PostgresTelegramInboxRepository,
    project_id: str,
) -> None:
    identity = _identity(project_id)
    await _insert(repo, identity, text="terminal")
    claimed = await repo.claim_next(
        owner_id="worker-a",
        owner_token="lease-a",
        lease_expires_at=await _db_time(repo.pool, seconds=60),
    )
    assert claimed is not None
    assert await repo.mark_terminal_failure(
        claimed.id,
        owner_token="lease-a",
        error_kind="invalid_update",
        error_message="bad payload",
    )

    duplicate = await _insert(repo, identity, text="terminal")

    assert duplicate.record.status is TelegramInboxStatus.TERMINAL_FAILED
    assert duplicate.record.attempt_count == 1
    assert duplicate.record.last_error_kind == "invalid_update"
    assert duplicate.record.last_error_message == "bad payload"
    assert duplicate.record.next_attempt_at is None


async def test_differing_payload_records_anomaly_without_overwrite(
    repo: PostgresTelegramInboxRepository,
    project_id: str,
) -> None:
    identity = _identity(project_id)
    inserted = await _insert(repo, identity, text="original")

    duplicate = await _insert(repo, identity, text="modified")

    assert duplicate.created is False
    assert duplicate.payload_anomaly is True
    assert duplicate.record.original_payload == inserted.record.original_payload
    assert duplicate.record.original_payload["message"]["text"] == "original"
    assert duplicate.record.payload_anomaly_count == 1
    assert duplicate.record.last_payload_anomaly_at is not None


async def test_concurrent_claim_allows_one_active_owner(
    repo: PostgresTelegramInboxRepository,
    project_id: str,
) -> None:
    await _insert(repo, _identity(project_id), text="claim")

    results = await asyncio.gather(
        repo.claim_next(
            owner_id="worker-a",
            owner_token="lease-a",
            lease_expires_at=await _db_time(repo.pool, seconds=60),
        ),
        repo.claim_next(
            owner_id="worker-b",
            owner_token="lease-b",
            lease_expires_at=await _db_time(repo.pool, seconds=60),
        ),
    )

    claims = [result for result in results if result is not None]
    assert len(claims) == 1
    assert claims[0].attempt_count == 1


async def test_claim_rejects_empty_owner_values(
    repo: PostgresTelegramInboxRepository,
    project_id: str,
) -> None:
    identity = _identity(project_id, update_id=970)
    await _insert(repo, identity, text="invalid-owner")
    record = await repo.get_by_identity(identity)
    assert record is not None

    invalid_cases = (
        {"owner_id": "", "owner_token": "lease-a"},
        {"owner_id": "   ", "owner_token": "lease-a"},
        {"owner_id": "worker-a", "owner_token": ""},
        {"owner_id": "worker-a", "owner_token": "   "},
    )
    for values in invalid_cases:
        with pytest.raises(ValueError):
            await repo.claim_next(
                **values,
                lease_expires_at=await _db_time(repo.pool, seconds=60),
            )
        with pytest.raises(ValueError):
            await repo.claim_by_id(
                record.id,
                **values,
                lease_expires_at=await _db_time(repo.pool, seconds=60),
            )


async def test_renew_reclaim_and_stale_owner_denial(
    repo: PostgresTelegramInboxRepository,
    project_id: str,
) -> None:
    await _insert(repo, _identity(project_id), text="lease")
    claimed = await repo.claim_next(
        owner_id="worker-a",
        owner_token="lease-a",
        lease_expires_at=await _db_time(repo.pool, seconds=60),
    )
    assert claimed is not None
    assert await repo.renew(
        claimed.id,
        owner_token="lease-a",
        lease_expires_at=await _db_time(repo.pool, seconds=120),
    )
    await _force_lease_expiry(repo.pool, claimed.id)
    assert await repo.reclaim_expired(claimed.id)
    reclaimed_after_expiry = await repo.get_by_identity(_identity(project_id))
    assert reclaimed_after_expiry is not None
    assert reclaimed_after_expiry.owned_by is None
    assert reclaimed_after_expiry.owner_token is None
    assert reclaimed_after_expiry.lease_expires_at is None

    assert not await repo.renew(
        claimed.id,
        owner_token="lease-a",
        lease_expires_at=await _db_time(repo.pool, seconds=180),
    )
    assert not await repo.complete(claimed.id, owner_token="lease-a")

    reclaimed = await repo.claim_next(
        owner_id="worker-b",
        owner_token="lease-b",
        lease_expires_at=await _db_time(repo.pool, seconds=240),
    )
    assert reclaimed is not None
    assert reclaimed.owner_token == "lease-b"
    assert reclaimed.attempt_count == 2


async def test_expired_owner_cannot_complete_or_fail_before_reclaim(
    repo: PostgresTelegramInboxRepository,
    project_id: str,
) -> None:
    await _insert(repo, _identity(project_id), text="expired-owner")
    claimed = await repo.claim_next(
        owner_id="worker-a",
        owner_token="lease-a",
        lease_expires_at=await _db_time(repo.pool, seconds=60),
    )
    assert claimed is not None
    await _force_lease_expiry(repo.pool, claimed.id)

    assert not await repo.complete(claimed.id, owner_token="lease-a")
    assert not await repo.mark_retryable_failure(
        claimed.id,
        owner_token="lease-a",
        error_kind="late_retryable",
        error_message="expired owner",
        next_attempt_at=_now(120),
    )
    assert not await repo.mark_terminal_failure(
        claimed.id,
        owner_token="lease-a",
        error_kind="late_terminal",
        error_message="expired owner",
    )

    reread = await repo.get_by_identity(_identity(project_id))
    assert reread is not None
    assert reread.status is TelegramInboxStatus.PROCESSING
    assert reread.owner_token == "lease-a"
    assert reread.attempt_count == 1


async def test_claim_rejects_zero_negative_or_already_expired_lease(
    repo: PostgresTelegramInboxRepository,
    project_id: str,
) -> None:
    await _insert(repo, _identity(project_id, update_id=910), text="expired-claim")
    expired_at = await _db_time(repo.pool, seconds=-30)

    assert (
        await repo.claim_next(
            owner_id="worker-a",
            owner_token="lease-a",
            lease_expires_at=expired_at,
        )
        is None
    )

    claimed = await repo.claim_next(
        owner_id="worker-b",
        owner_token="lease-b",
        lease_expires_at=await _db_time(repo.pool, seconds=60),
    )
    assert claimed is not None


async def test_renew_rejects_past_expiry_and_shortening(
    repo: PostgresTelegramInboxRepository,
    project_id: str,
) -> None:
    await _insert(repo, _identity(project_id, update_id=920), text="renew")
    claimed = await repo.claim_next(
        owner_id="worker-a",
        owner_token="lease-a",
        lease_expires_at=await _db_time(repo.pool, seconds=120),
    )
    assert claimed is not None

    assert not await repo.renew(
        claimed.id,
        owner_token="lease-a",
        lease_expires_at=await _db_time(repo.pool, seconds=-30),
    )
    assert not await repo.renew(
        claimed.id,
        owner_token="lease-a",
        lease_expires_at=claimed.lease_expires_at - timedelta(seconds=1),
    )
    assert await repo.renew(
        claimed.id,
        owner_token="lease-a",
        lease_expires_at=await _db_time(repo.pool, seconds=180),
    )


async def test_db_clock_not_caller_clock_determines_expiration(
    repo: PostgresTelegramInboxRepository,
    project_id: str,
) -> None:
    identity = _identity(project_id, update_id=930)
    await _insert(repo, identity, text="db-clock")
    claimed = await repo.claim_next(
        owner_id="worker-a",
        owner_token="lease-a",
        lease_expires_at=await _db_time(repo.pool, seconds=60),
    )
    assert claimed is not None
    await _force_lease_expiry(repo.pool, claimed.id)

    assert not await repo.complete(
        claimed.id,
        owner_token="lease-a",
    )
    assert not await repo.mark_terminal_failure(
        claimed.id,
        owner_token="lease-a",
        error_kind="late",
        error_message="caller timestamp is stale",
    )

    reread = await repo.get_by_identity(identity)
    assert reread is not None
    assert reread.status is TelegramInboxStatus.PROCESSING
    assert reread.owner_token == "lease-a"


async def test_complete_retryable_and_terminal_failure_transitions(
    repo: PostgresTelegramInboxRepository,
    project_id: str,
) -> None:
    complete_identity = _identity(project_id, update_id=1)
    retry_identity = _identity(project_id, update_id=2)
    terminal_identity = _identity(project_id, update_id=3)
    await _insert(repo, complete_identity, text="complete")
    await _insert(repo, retry_identity, text="retry")
    await _insert(repo, terminal_identity, text="terminal")

    complete_claim = await repo.claim_by_id(
        (await repo.get_by_identity(complete_identity)).id,
        owner_id="worker-a",
        owner_token="lease-a",
        lease_expires_at=await _db_time(repo.pool, seconds=60),
    )
    retry_claim = await repo.claim_by_id(
        (await repo.get_by_identity(retry_identity)).id,
        owner_id="worker-b",
        owner_token="lease-b",
        lease_expires_at=await _db_time(repo.pool, seconds=60),
    )
    terminal_claim = await repo.claim_by_id(
        (await repo.get_by_identity(terminal_identity)).id,
        owner_id="worker-c",
        owner_token="lease-c",
        lease_expires_at=await _db_time(repo.pool, seconds=60),
    )

    assert complete_claim is not None
    assert retry_claim is not None
    assert terminal_claim is not None
    assert await repo.complete(complete_claim.id, owner_token="lease-a")
    assert await repo.mark_retryable_failure(
        retry_claim.id,
        owner_token="lease-b",
        error_kind="temporary",
        error_message="retry later",
        next_attempt_at=_now(120),
    )
    assert await repo.mark_terminal_failure(
        terminal_claim.id,
        owner_token="lease-c",
        error_kind="invalid_update",
        error_message="bad payload",
    )

    assert (
        await repo.get_by_identity(complete_identity)
    ).status is TelegramInboxStatus.COMPLETED
    assert (
        await repo.get_by_identity(retry_identity)
    ).status is TelegramInboxStatus.RETRYABLE_FAILED
    assert (
        await repo.get_by_identity(terminal_identity)
    ).status is TelegramInboxStatus.TERMINAL_FAILED

    for identity in (complete_identity, retry_identity, terminal_identity):
        reread = await repo.get_by_identity(identity)
        assert reread is not None
        assert reread.owned_by is None
        assert reread.owner_token is None
        assert reread.lease_expires_at is None


async def test_bounded_error_kind_and_message_are_persisted(
    repo: PostgresTelegramInboxRepository,
    project_id: str,
) -> None:
    identity = _identity(project_id, update_id=940)
    await _insert(repo, identity, text="bounded")
    claimed = await repo.claim_next(
        owner_id="worker-a",
        owner_token="lease-a",
        lease_expires_at=await _db_time(repo.pool, seconds=60),
    )
    assert claimed is not None

    assert await repo.mark_retryable_failure(
        claimed.id,
        owner_token="lease-a",
        error_kind="k" * 200,
        error_message="m" * 2500,
        next_attempt_at=await _db_time(repo.pool, seconds=60),
    )

    reread = await repo.get_by_identity(identity)
    assert reread is not None
    assert reread.last_error_kind == "k" * 128
    assert reread.last_error_message == "m" * 2000


async def test_attempt_count_increments_only_on_real_claim(
    repo: PostgresTelegramInboxRepository,
    project_id: str,
) -> None:
    identity = _identity(project_id)
    await _insert(repo, identity, text="attempt")
    duplicate_before_claim = await _insert(repo, identity, text="attempt")
    claimed = await repo.claim_next(
        owner_id="worker-a",
        owner_token="lease-a",
        lease_expires_at=await _db_time(repo.pool, seconds=60),
    )
    assert claimed is not None
    duplicate_during_claim = await _insert(repo, identity, text="attempt")

    assert duplicate_before_claim.record.attempt_count == 0
    assert claimed.attempt_count == 1
    assert duplicate_during_claim.record.attempt_count == 1


async def test_expired_processing_batch_recovery_is_atomic_and_invalidates_old_owner(
    repo: PostgresTelegramInboxRepository,
    project_id: str,
) -> None:
    identity = _identity(project_id, update_id=950)
    await _insert(repo, identity, text="batch-recovery")
    claimed = await repo.claim_next(
        owner_id="worker-a",
        owner_token="lease-a",
        lease_expires_at=await _db_time(repo.pool, seconds=60),
    )
    assert claimed is not None
    await _force_lease_expiry(repo.pool, claimed.id)

    first, second = await asyncio.gather(
        repo.reclaim_expired_batch(limit=1),
        repo.reclaim_expired_batch(limit=1),
    )
    reclaimed = [record for batch in (first, second) for record in batch]

    assert len(reclaimed) == 1
    assert reclaimed[0].id == claimed.id
    assert reclaimed[0].status is TelegramInboxStatus.RETRYABLE_FAILED
    assert reclaimed[0].owned_by is None
    assert reclaimed[0].owner_token is None
    assert reclaimed[0].lease_expires_at is None
    assert not await repo.complete(claimed.id, owner_token="lease-a")

    next_claim = await repo.claim_next(
        owner_id="worker-b",
        owner_token="lease-b",
        lease_expires_at=await _db_time(repo.pool, seconds=60),
    )
    assert next_claim is not None
    assert next_claim.id == claimed.id
    assert next_claim.attempt_count == 2


async def test_recovery_discovery_survives_pool_reconstruction() -> None:
    migration_sql = MIGRATION.read_text(encoding="utf-8")
    first_pool = await asyncpg.create_pool(
        settings.DATABASE_URL, min_size=1, max_size=5
    )
    async with first_pool.acquire() as conn:
        await _ensure_base_projects_schema(conn)
        await conn.execute(migration_sql)
        project_id = str(
            await conn.fetchval(
                "INSERT INTO projects (name) VALUES ($1) RETURNING id",
                f"S1.1 recovery {uuid4()}",
            )
        )

    identity = _identity(project_id, update_id=960)
    first_repo = PostgresTelegramInboxRepository(first_pool)
    await _insert(first_repo, identity, text="recover")
    claimed = await first_repo.claim_next(
        owner_id="worker-a",
        owner_token="lease-a",
        lease_expires_at=await _db_time(first_pool, seconds=60),
    )
    assert claimed is not None
    await _force_lease_expiry(first_pool, claimed.id)
    await first_pool.close()

    new_pool = await asyncpg.create_pool(settings.DATABASE_URL, min_size=1, max_size=5)
    try:
        second_repo = PostgresTelegramInboxRepository(new_pool)
        recovered = await second_repo.reclaim_expired_batch(limit=10)
        next_claim = await second_repo.claim_next(
            owner_id="worker-b",
            owner_token="lease-b",
            lease_expires_at=await _db_time(new_pool, seconds=60),
        )
    finally:
        await new_pool.close()

    assert [record.id for record in recovered] == [claimed.id]
    assert next_claim is not None
    assert next_claim.id == claimed.id
    assert next_claim.owner_token == "lease-b"
    assert next_claim.attempt_count == 2


async def test_pool_reconstruction_readback_preserves_identity_payload_and_lifecycle() -> (
    None
):
    migration_sql = MIGRATION.read_text(encoding="utf-8")
    first_pool = await asyncpg.create_pool(
        settings.DATABASE_URL, min_size=1, max_size=5
    )
    async with first_pool.acquire() as conn:
        await _ensure_base_projects_schema(conn)
        await conn.execute(migration_sql)
        project_id = str(
            await conn.fetchval(
                "INSERT INTO projects (name) VALUES ($1) RETURNING id",
                f"S1.1 reconstruction {uuid4()}",
            )
        )

    identity = _identity(project_id)
    first_repo = PostgresTelegramInboxRepository(first_pool)
    inserted = await _insert(first_repo, identity, text="persisted")

    await first_pool.close()
    new_pool = await asyncpg.create_pool(settings.DATABASE_URL, min_size=1, max_size=5)
    try:
        second_repo = PostgresTelegramInboxRepository(new_pool)
        reread = await second_repo.get_by_identity(identity)
    finally:
        await new_pool.close()

    assert reread is not None
    assert reread.id == inserted.record.id
    assert reread.identity == identity
    assert reread.original_payload == inserted.record.original_payload
    assert reread.status is TelegramInboxStatus.RECEIVED


async def test_project_and_platform_bot_id_storage_reject_invalid_non_null_ids(
    migrated_pool,
    project_id: str,
) -> None:
    inbox_repo = PostgresTelegramInboxRepository(migrated_pool)
    async with migrated_pool.acquire() as conn:
        for column in ("client_telegram_bot_id", "manager_telegram_bot_id"):
            with pytest.raises(asyncpg.CheckViolationError):
                await conn.execute(
                    f"UPDATE projects SET {column} = $1 WHERE id = $2",
                    0,
                    project_id,
                )

    with pytest.raises(ValueError):
        await inbox_repo.set_platform_telegram_bot_id("platform_admin", 0)
    with pytest.raises(ValueError):
        await inbox_repo.set_platform_telegram_bot_id("platform_admin", -1)


async def _ensure_base_projects_schema(conn: asyncpg.Connection) -> None:
    await conn.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS public.projects (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
        """
    )
