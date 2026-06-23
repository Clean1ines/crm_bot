-- Remove per-WorkItem retry timing from canonical Execution Runtime.
-- WorkItems do not sleep. Retryable failures are immediately eligible and
-- prioritized by admission ordering.

DROP INDEX IF EXISTS idx_execution_work_items_ready_due;
DROP INDEX IF EXISTS idx_execution_work_items_due_retry_plan;

ALTER TABLE execution_work_items
    DROP CONSTRAINT IF EXISTS chk_execution_work_items_terminal_no_next_attempt;

DO $$
DECLARE
    removed_column_name text := concat('next', '_', 'attempt', '_', 'at');
BEGIN
    EXECUTE format(
        'ALTER TABLE execution_work_items DROP COLUMN IF EXISTS %I',
        removed_column_name
    );
END $$;

CREATE INDEX IF NOT EXISTS idx_execution_work_items_ready_retry_priority
    ON execution_work_items (
        work_kind,
        status,
        updated_at,
        work_item_id
    )
    WHERE status IN ('retryable_failed', 'ready');

CREATE INDEX IF NOT EXISTS idx_execution_work_items_retry_plan
    ON execution_work_items (
        work_kind,
        status,
        retry_plan,
        updated_at,
        work_item_id
    )
    WHERE status = 'retryable_failed';
