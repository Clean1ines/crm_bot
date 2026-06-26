from pathlib import Path


MIGRATION_PATH = Path(
    "migrations/117_create_capacity_admission_queue_runtime_tables.sql"
)


def _migration_sql() -> str:
    return MIGRATION_PATH.read_text(encoding="utf-8")


def test_capacity_admission_queue_runtime_migration_exists() -> None:
    sql = _migration_sql()

    assert "CREATE TABLE IF NOT EXISTS capacity_admission_work_items" in sql
    assert "CREATE TABLE IF NOT EXISTS capacity_admission_lane_dirty_flags" in sql
    assert "CREATE TABLE IF NOT EXISTS capacity_admission_lane_events" in sql
    assert "CREATE TABLE IF NOT EXISTS capacity_admission_lane_claims" in sql
    assert "CREATE TABLE IF NOT EXISTS capacity_admission_event_cursors" in sql


def test_capacity_admission_work_items_projection_has_required_contract_columns() -> (
    None
):
    sql = _migration_sql()

    assert "work_item_id TEXT PRIMARY KEY" in sql
    assert "REFERENCES execution_work_items(work_item_id)" in sql
    assert "work_kind TEXT NOT NULL" in sql
    assert "workflow_run_id TEXT NULL" in sql
    assert "project_id TEXT NULL" in sql
    assert "provider TEXT NOT NULL" in sql
    assert "account_ref TEXT NULL" in sql
    assert "model_ref TEXT NOT NULL" in sql
    assert "status TEXT NOT NULL" in sql
    assert "retry_plan TEXT NULL" in sql
    assert "input_tokens INTEGER NOT NULL" in sql
    assert "artifact_tokens INTEGER NOT NULL" in sql
    assert "required_window_tokens INTEGER NOT NULL" in sql
    assert "source_ref JSONB NOT NULL DEFAULT '{}'::jsonb" in sql


def test_capacity_admission_work_items_status_contract_is_projection_not_new_lifecycle() -> (
    None
):
    sql = _migration_sql()

    assert "chk_capacity_admission_work_items_status" in sql
    assert "'ready'" in sql
    assert "'leased'" in sql
    assert "'retryable_failed'" in sql
    assert "'completed'" in sql
    assert "'terminal_failed'" in sql
    assert "'cancelled'" in sql
    assert "'split_superseded'" in sql
    assert "'user_action_required'" in sql


def test_capacity_admission_work_items_token_contract_is_not_jsonb_hot_path() -> None:
    sql = _migration_sql()

    assert "input_tokens > 0" in sql
    assert "artifact_tokens >= 0" in sql
    assert "required_window_tokens >= input_tokens" in sql
    assert "required_window_tokens >= input_tokens + artifact_tokens" in sql


def test_capacity_admission_fit_indexes_are_retry_then_ready_specific() -> None:
    sql = _migration_sql()

    assert "idx_capacity_admission_retry_fit" in sql
    assert "WHERE status = 'retryable_failed'" in sql
    assert "idx_capacity_admission_ready_fit" in sql
    assert "WHERE status = 'ready'" in sql
    assert (
        "provider,\n        model_ref,\n        work_kind,\n        required_window_tokens,\n        updated_at,\n        work_item_id"
        in sql
    )


def test_capacity_admission_lane_dirty_flags_are_coalesced_and_claimable() -> None:
    sql = _migration_sql()

    assert "capacity_admission_lane_dirty_flags" in sql
    assert "lane_id TEXT PRIMARY KEY" in sql
    assert "dirty_reason TEXT NOT NULL" in sql
    assert "dirty_count INTEGER NOT NULL DEFAULT 1" in sql
    assert "first_marked_at TIMESTAMPTZ NOT NULL" in sql
    assert "last_marked_at TIMESTAMPTZ NOT NULL" in sql
    assert "claimed_by TEXT NULL" in sql
    assert "claimed_until TIMESTAMPTZ NULL" in sql
    assert "idx_capacity_admission_lane_dirty_claimable" in sql
    assert "idx_capacity_admission_lane_dirty_expired_claim" in sql


def test_capacity_admission_lane_events_are_durable_outbox_like_events() -> None:
    sql = _migration_sql()

    assert "capacity_admission_lane_events" in sql
    assert "sequence_number BIGSERIAL PRIMARY KEY" in sql
    assert "event_id UUID NOT NULL UNIQUE" in sql
    assert "'DueWorkQueueChanged'" in sql
    assert "'CapacityWindowChanged'" in sql
    assert "'CapacityAdmissionPassRequested'" in sql
    assert "'CapacityWindowLeasedWorkItem'" in sql
    assert "payload JSONB NOT NULL DEFAULT '{}'::jsonb" in sql
    assert "occurred_at TIMESTAMPTZ NOT NULL" in sql


def test_capacity_admission_lane_claims_and_cursors_support_crash_safe_dispatch() -> (
    None
):
    sql = _migration_sql()

    assert "capacity_admission_lane_claims" in sql
    assert "claimed_by TEXT NOT NULL" in sql
    assert "claimed_until TIMESTAMPTZ NOT NULL" in sql
    assert "claim_version BIGINT NOT NULL DEFAULT 1" in sql
    assert "idx_capacity_admission_lane_claims_expiry" in sql

    assert "capacity_admission_event_cursors" in sql
    assert "consumer_name TEXT PRIMARY KEY" in sql
    assert "last_sequence_number BIGINT NOT NULL DEFAULT 0" in sql
    assert "last_sequence_number >= 0" in sql


def test_capacity_admission_schema_contract_does_not_reintroduce_prefix_scan_vocabulary() -> (
    None
):
    sql = _migration_sql()

    forbidden_markers = (
        "candidate_scan_limit",
        "_candidate_scan_limit",
        "_CANDIDATE_SCAN_MULTIPLIER",
        "_CANDIDATE_SCAN_EXTRA_CAP",
        "requested_items * 4",
    )

    for marker in forbidden_markers:
        assert marker not in sql
