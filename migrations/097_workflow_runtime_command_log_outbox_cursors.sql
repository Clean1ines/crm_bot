CREATE TABLE IF NOT EXISTS workflow_runtime_command_log (
    command_id TEXT PRIMARY KEY,
    command_type TEXT NOT NULL,
    workflow_run_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    payload JSONB NOT NULL,
    status TEXT NOT NULL,
    run_after TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    causation_event_id TEXT NULL,
    correlation_id TEXT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    CONSTRAINT workflow_runtime_command_log_attempt_count_non_negative
        CHECK (attempt_count >= 0)
);

CREATE INDEX IF NOT EXISTS idx_workflow_runtime_command_log_workflow_run_id
    ON workflow_runtime_command_log (workflow_run_id);

CREATE INDEX IF NOT EXISTS idx_workflow_runtime_command_log_status_run_after
    ON workflow_runtime_command_log (status, run_after);

CREATE TABLE IF NOT EXISTS workflow_runtime_outbox_events (
    sequence_number BIGSERIAL PRIMARY KEY,
    event_id TEXT NOT NULL UNIQUE,
    event_type TEXT NOT NULL,
    workflow_run_id TEXT NOT NULL,
    payload JSONB NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    causation_command_id TEXT NULL,
    correlation_id TEXT NULL
);

CREATE INDEX IF NOT EXISTS idx_workflow_runtime_outbox_events_workflow_run_id
    ON workflow_runtime_outbox_events (workflow_run_id);

CREATE INDEX IF NOT EXISTS idx_workflow_runtime_outbox_events_event_type
    ON workflow_runtime_outbox_events (event_type);

CREATE TABLE IF NOT EXISTS workflow_runtime_event_cursors (
    consumer_ref TEXT PRIMARY KEY,
    last_seen_sequence_number BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT workflow_runtime_event_cursors_last_seen_non_negative
        CHECK (last_seen_sequence_number >= 0)
);
