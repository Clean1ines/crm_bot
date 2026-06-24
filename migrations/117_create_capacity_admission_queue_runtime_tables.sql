-- Capacity Admission Queue Runtime
--
-- This migration creates the durable projection and lane wakeup state used by
-- capacity-based admission. It intentionally does not change WorkItem lifecycle,
-- LLM provider execution, Workbench semantics, or frontend reducers.

CREATE TABLE IF NOT EXISTS capacity_admission_work_items (
    work_item_id TEXT PRIMARY KEY
        REFERENCES execution_work_items(work_item_id)
        ON DELETE CASCADE,
    work_kind TEXT NOT NULL,
    workflow_run_id UUID NULL,
    project_id UUID NULL,
    provider TEXT NOT NULL,
    account_ref TEXT NULL,
    model_ref TEXT NOT NULL,
    status TEXT NOT NULL,
    retry_plan TEXT NULL,
    estimated_input_tokens INTEGER NOT NULL,
    estimated_output_tokens INTEGER NOT NULL,
    effective_output_cap_tokens INTEGER NOT NULL,
    reserved_total_tokens INTEGER NOT NULL,
    source_ref JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT chk_capacity_admission_work_items_status
        CHECK (
            status IN (
                'ready',
                'leased',
                'retryable_failed',
                'completed',
                'terminal_failed',
                'cancelled',
                'split_superseded',
                'user_action_required'
            )
        ),
    CONSTRAINT chk_capacity_admission_work_items_token_estimates
        CHECK (
            estimated_input_tokens > 0
            AND estimated_output_tokens >= 0
            AND effective_output_cap_tokens >= estimated_output_tokens
            AND reserved_total_tokens >= estimated_input_tokens
            AND reserved_total_tokens >= estimated_input_tokens + estimated_output_tokens
        ),
    CONSTRAINT chk_capacity_admission_work_items_non_empty_text
        CHECK (
            length(trim(work_item_id)) > 0
            AND length(trim(work_kind)) > 0
            AND length(trim(provider)) > 0
            AND length(trim(model_ref)) > 0
            AND (
                account_ref IS NULL
                OR length(trim(account_ref)) > 0
            )
        )
);

CREATE INDEX IF NOT EXISTS idx_capacity_admission_retry_fit
    ON capacity_admission_work_items (
        provider,
        model_ref,
        work_kind,
        reserved_total_tokens,
        updated_at,
        work_item_id
    )
    WHERE status = 'retryable_failed';

CREATE INDEX IF NOT EXISTS idx_capacity_admission_ready_fit
    ON capacity_admission_work_items (
        provider,
        model_ref,
        work_kind,
        reserved_total_tokens,
        updated_at,
        work_item_id
    )
    WHERE status = 'ready';

CREATE INDEX IF NOT EXISTS idx_capacity_admission_work_items_lane_state
    ON capacity_admission_work_items (
        provider,
        model_ref,
        work_kind,
        status,
        updated_at,
        work_item_id
    );

CREATE TABLE IF NOT EXISTS capacity_admission_lane_dirty_flags (
    lane_id TEXT PRIMARY KEY,
    work_kind TEXT NOT NULL,
    provider TEXT NOT NULL,
    account_ref TEXT NULL,
    model_ref TEXT NOT NULL,
    dirty_reason TEXT NOT NULL,
    dirty_count INTEGER NOT NULL DEFAULT 1,
    first_marked_at TIMESTAMPTZ NOT NULL,
    last_marked_at TIMESTAMPTZ NOT NULL,
    claimed_by TEXT NULL,
    claimed_until TIMESTAMPTZ NULL,
    CONSTRAINT chk_capacity_admission_lane_dirty_flags_dirty_count
        CHECK (dirty_count > 0),
    CONSTRAINT chk_capacity_admission_lane_dirty_flags_non_empty_text
        CHECK (
            length(trim(lane_id)) > 0
            AND length(trim(work_kind)) > 0
            AND length(trim(provider)) > 0
            AND length(trim(model_ref)) > 0
            AND length(trim(dirty_reason)) > 0
            AND (
                account_ref IS NULL
                OR length(trim(account_ref)) > 0
            )
            AND (
                claimed_by IS NULL
                OR length(trim(claimed_by)) > 0
            )
        ),
    CONSTRAINT chk_capacity_admission_lane_dirty_flags_claim_pair
        CHECK (
            (claimed_by IS NULL AND claimed_until IS NULL)
            OR (claimed_by IS NOT NULL AND claimed_until IS NOT NULL)
        )
);

CREATE INDEX IF NOT EXISTS idx_capacity_admission_lane_dirty_claimable
    ON capacity_admission_lane_dirty_flags (
        last_marked_at,
        lane_id
    )
    WHERE claimed_until IS NULL;

CREATE INDEX IF NOT EXISTS idx_capacity_admission_lane_dirty_expired_claim
    ON capacity_admission_lane_dirty_flags (
        claimed_until,
        lane_id
    )
    WHERE claimed_until IS NOT NULL;

CREATE TABLE IF NOT EXISTS capacity_admission_lane_events (
    sequence_number BIGSERIAL PRIMARY KEY,
    event_id UUID NOT NULL UNIQUE,
    lane_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    work_kind TEXT NOT NULL,
    provider TEXT NOT NULL,
    account_ref TEXT NULL,
    model_ref TEXT NOT NULL,
    work_item_id TEXT NULL,
    reason TEXT NOT NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    occurred_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT chk_capacity_admission_lane_events_event_type
        CHECK (
            event_type IN (
                'DueWorkQueueChanged',
                'CapacityWindowChanged',
                'CapacityAdmissionPassRequested',
                'CapacityWindowLeasedWorkItem'
            )
        ),
    CONSTRAINT chk_capacity_admission_lane_events_non_empty_text
        CHECK (
            length(trim(lane_id)) > 0
            AND length(trim(event_type)) > 0
            AND length(trim(work_kind)) > 0
            AND length(trim(provider)) > 0
            AND length(trim(model_ref)) > 0
            AND length(trim(reason)) > 0
            AND (
                account_ref IS NULL
                OR length(trim(account_ref)) > 0
            )
            AND (
                work_item_id IS NULL
                OR length(trim(work_item_id)) > 0
            )
        )
);

CREATE INDEX IF NOT EXISTS idx_capacity_admission_lane_events_lane_sequence
    ON capacity_admission_lane_events (
        lane_id,
        sequence_number
    );

CREATE INDEX IF NOT EXISTS idx_capacity_admission_lane_events_type_sequence
    ON capacity_admission_lane_events (
        event_type,
        sequence_number
    );

CREATE TABLE IF NOT EXISTS capacity_admission_lane_claims (
    lane_id TEXT PRIMARY KEY,
    work_kind TEXT NOT NULL,
    provider TEXT NOT NULL,
    account_ref TEXT NULL,
    model_ref TEXT NOT NULL,
    claimed_by TEXT NOT NULL,
    claimed_until TIMESTAMPTZ NOT NULL,
    claimed_at TIMESTAMPTZ NOT NULL,
    claim_version BIGINT NOT NULL DEFAULT 1,
    CONSTRAINT chk_capacity_admission_lane_claims_claim_version
        CHECK (claim_version > 0),
    CONSTRAINT chk_capacity_admission_lane_claims_non_empty_text
        CHECK (
            length(trim(lane_id)) > 0
            AND length(trim(work_kind)) > 0
            AND length(trim(provider)) > 0
            AND length(trim(model_ref)) > 0
            AND length(trim(claimed_by)) > 0
            AND (
                account_ref IS NULL
                OR length(trim(account_ref)) > 0
            )
        )
);

CREATE INDEX IF NOT EXISTS idx_capacity_admission_lane_claims_expiry
    ON capacity_admission_lane_claims (
        claimed_until,
        lane_id
    );

CREATE TABLE IF NOT EXISTS capacity_admission_event_cursors (
    consumer_name TEXT PRIMARY KEY,
    last_sequence_number BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT chk_capacity_admission_event_cursors_sequence
        CHECK (last_sequence_number >= 0),
    CONSTRAINT chk_capacity_admission_event_cursors_consumer_name
        CHECK (length(trim(consumer_name)) > 0)
);
