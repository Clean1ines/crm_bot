CREATE TABLE IF NOT EXISTS workflow_runtime_progress_snapshots (
    workflow_run_id TEXT PRIMARY KEY,
    current_phase TEXT NOT NULL,
    workflow_status TEXT NOT NULL,
    total_work_items INTEGER NOT NULL DEFAULT 0,
    scheduled_work_items INTEGER NOT NULL DEFAULT 0,
    running_work_items INTEGER NOT NULL DEFAULT 0,
    completed_work_items INTEGER NOT NULL DEFAULT 0,
    deferred_work_items INTEGER NOT NULL DEFAULT 0,
    retryable_failed_work_items INTEGER NOT NULL DEFAULT 0,
    terminal_failed_work_items INTEGER NOT NULL DEFAULT 0,
    blocked_work_items INTEGER NOT NULL DEFAULT 0,
    domain_counters JSONB NOT NULL DEFAULT '{}'::jsonb,
    started_at TIMESTAMPTZ NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ NULL,
    CONSTRAINT workflow_runtime_progress_snapshots_total_non_negative
        CHECK (total_work_items >= 0),
    CONSTRAINT workflow_runtime_progress_snapshots_scheduled_non_negative
        CHECK (scheduled_work_items >= 0),
    CONSTRAINT workflow_runtime_progress_snapshots_running_non_negative
        CHECK (running_work_items >= 0),
    CONSTRAINT workflow_runtime_progress_snapshots_completed_non_negative
        CHECK (completed_work_items >= 0),
    CONSTRAINT workflow_runtime_progress_snapshots_deferred_non_negative
        CHECK (deferred_work_items >= 0),
    CONSTRAINT workflow_runtime_progress_snapshots_retryable_failed_non_negative
        CHECK (retryable_failed_work_items >= 0),
    CONSTRAINT workflow_runtime_progress_snapshots_terminal_failed_non_negative
        CHECK (terminal_failed_work_items >= 0),
    CONSTRAINT workflow_runtime_progress_snapshots_blocked_non_negative
        CHECK (blocked_work_items >= 0)
);

CREATE TABLE IF NOT EXISTS workflow_runtime_timeline_entries (
    timeline_entry_id TEXT PRIMARY KEY,
    workflow_run_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    phase TEXT NOT NULL,
    severity TEXT NOT NULL,
    message TEXT NOT NULL,
    payload_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    occurred_at TIMESTAMPTZ NOT NULL,
    source_ref TEXT NULL,
    work_item_id TEXT NULL,
    attempt_id TEXT NULL
);

CREATE INDEX IF NOT EXISTS idx_workflow_runtime_timeline_entries_workflow_occurred
    ON workflow_runtime_timeline_entries (workflow_run_id, occurred_at DESC);

CREATE INDEX IF NOT EXISTS idx_workflow_runtime_timeline_entries_workflow_event_type
    ON workflow_runtime_timeline_entries (workflow_run_id, event_type);

CREATE TABLE IF NOT EXISTS workflow_runtime_resource_usage_snapshots (
    workflow_run_id TEXT PRIMARY KEY,
    request_count INTEGER NOT NULL DEFAULT 0,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    estimated_cost_microusd BIGINT NOT NULL DEFAULT 0,
    duration_ms BIGINT NOT NULL DEFAULT 0,
    provider_breakdown JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT workflow_runtime_resource_usage_request_count_non_negative
        CHECK (request_count >= 0),
    CONSTRAINT workflow_runtime_resource_usage_input_tokens_non_negative
        CHECK (input_tokens >= 0),
    CONSTRAINT workflow_runtime_resource_usage_output_tokens_non_negative
        CHECK (output_tokens >= 0),
    CONSTRAINT workflow_runtime_resource_usage_total_tokens_non_negative
        CHECK (total_tokens >= 0),
    CONSTRAINT workflow_runtime_resource_usage_cost_non_negative
        CHECK (estimated_cost_microusd >= 0),
    CONSTRAINT workflow_runtime_resource_usage_duration_non_negative
        CHECK (duration_ms >= 0)
);
