from pathlib import Path


MIGRATION = Path("migrations/132_create_telegram_inbox.sql")


def test_telegram_inbox_migration_exists_and_is_forward_fix_safe() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    assert "ADD COLUMN IF NOT EXISTS client_telegram_bot_id" in source
    assert "ADD COLUMN IF NOT EXISTS manager_telegram_bot_id" in source
    assert (
        "CREATE TABLE IF NOT EXISTS public.platform_telegram_bot_configurations"
        in source
    )
    assert "CREATE TABLE IF NOT EXISTS public.telegram_inbox_updates" in source
    assert (
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_telegram_inbox_project_update_identity"
        in source
    )
    assert (
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_telegram_inbox_platform_update_identity"
        in source
    )
    assert "duplicate_count" in source
    assert "payload_anomaly_count" in source
    assert "ck_projects_client_telegram_bot_id_positive" in source
    assert "ck_projects_manager_telegram_bot_id_positive" in source
    assert "ck_platform_telegram_bot_id_positive" in source
    assert "CHECK" in source
    assert "bot_token" not in source.lower()
    assert "webhook_secret" not in source.lower()


def test_telegram_inbox_migration_uses_numeric_bot_identity_not_secret_identity() -> (
    None
):
    source = MIGRATION.read_text(encoding="utf-8").lower()

    assert "telegram_bot_id bigint" in source
    assert "telegram_update_id bigint" in source
    assert "client_bot_username" not in source
    assert "manager_bot_username" not in source
    assert "token_hash" not in source
    assert "generation" not in source
