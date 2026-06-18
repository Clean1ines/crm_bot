-- Persist canonical Execution Runtime retry intent separately from lifecycle status.
-- Status says whether work is ready/leased/retryable/terminal.
-- retry_plan says how a retryable work item should be retried.

ALTER TABLE execution_work_items
    ADD COLUMN IF NOT EXISTS retry_plan text NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_execution_work_items_retry_plan'
    ) THEN
        ALTER TABLE execution_work_items
            ADD CONSTRAINT chk_execution_work_items_retry_plan
            CHECK (
                retry_plan IS NULL
                OR retry_plan IN (
                    'retry_same_model',
                    'retry_other_org',
                    'retry_special_empty_claims_check_model',
                    'retry_larger_context_model',
                    'retry_larger_output_model',
                    'retry_daily_fallback_model',
                    'wait_nearest_capacity_window',
                    'split_source_unit',
                    'wait_daily_capacity_reset',
                    'terminal'
                )
            );
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_execution_work_items_due_retry_plan
    ON execution_work_items (work_kind, status, retry_plan, next_attempt_at, updated_at)
    WHERE status = 'retryable_failed';
