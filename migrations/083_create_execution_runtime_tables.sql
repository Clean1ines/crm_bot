-- Canonical Execution Runtime persistence.
-- Do not map these entities onto legacy Workbench section batch queues.

CREATE TABLE IF NOT EXISTS execution_work_items (
    work_item_id text PRIMARY KEY,
    work_kind text NOT NULL,
    status text NOT NULL,
    attempt_count integer NOT NULL DEFAULT 0,
    leased_by text NULL,
    lease_token text NULL,
    lease_expires_at timestamptz NULL,
    last_error_kind text NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT chk_execution_work_items_id_non_empty
        CHECK (length(trim(work_item_id)) > 0),

    CONSTRAINT chk_execution_work_items_kind_non_empty
        CHECK (length(trim(work_kind)) > 0),

    CONSTRAINT chk_execution_work_items_status
        CHECK (
            status IN (
                'ready',
                'leased',
                'retryable_failed',
                'terminal_failed',
                'completed',
                'cancelled',
                'split_superseded',
                'user_action_required'
            )
        ),

    CONSTRAINT chk_execution_work_items_attempt_count_non_negative
        CHECK (attempt_count >= 0),

    CONSTRAINT chk_execution_work_items_lease_shape
        CHECK (
            (
                status = 'leased'
                AND leased_by IS NOT NULL
                AND lease_token IS NOT NULL
                AND lease_expires_at IS NOT NULL
            )
            OR
            (
                status <> 'leased'
                AND leased_by IS NULL
                AND lease_token IS NULL
                AND lease_expires_at IS NULL
            )
        ),

    CONSTRAINT chk_execution_work_items_updated_after_created
        CHECK (updated_at >= created_at)
);

CREATE TABLE IF NOT EXISTS execution_work_item_attempts (
    attempt_id text PRIMARY KEY,
    work_item_id text NOT NULL REFERENCES execution_work_items(work_item_id) ON DELETE CASCADE,
    attempt_number integer NOT NULL,
    started_at timestamptz NOT NULL,
    finished_at timestamptz NULL,
    outcome_status text NULL,
    error_kind text NULL,
    created_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT chk_execution_work_item_attempts_id_non_empty
        CHECK (length(trim(attempt_id)) > 0),

    CONSTRAINT chk_execution_work_item_attempts_work_item_id_non_empty
        CHECK (length(trim(work_item_id)) > 0),

    CONSTRAINT chk_execution_work_item_attempts_attempt_number_positive
        CHECK (attempt_number >= 1),

    CONSTRAINT chk_execution_work_item_attempts_finished_after_started
        CHECK (finished_at IS NULL OR finished_at >= started_at),

    CONSTRAINT uq_execution_work_item_attempts_work_item_attempt
        UNIQUE (work_item_id, attempt_number)
);

CREATE INDEX IF NOT EXISTS idx_execution_work_items_ready_retry_priority
    ON execution_work_items (work_kind, status, updated_at, work_item_id)
    WHERE status IN ('retryable_failed', 'ready');

CREATE INDEX IF NOT EXISTS idx_execution_work_items_lease_expiry
    ON execution_work_items (status, lease_expires_at)
    WHERE status = 'leased';

CREATE INDEX IF NOT EXISTS idx_execution_work_items_user_action
    ON execution_work_items (work_kind, status, updated_at)
    WHERE status = 'user_action_required';

CREATE INDEX IF NOT EXISTS idx_execution_work_item_attempts_work_item
    ON execution_work_item_attempts (work_item_id, attempt_number);
