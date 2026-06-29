ALTER TABLE execution_work_items
ADD COLUMN IF NOT EXISTS next_attempt_at timestamptz NULL;

CREATE INDEX IF NOT EXISTS idx_execution_work_items_due
ON execution_work_items (work_kind, status, next_attempt_at, updated_at);

CREATE INDEX IF NOT EXISTS idx_execution_work_items_retry_plan_due
ON execution_work_items (work_kind, status, retry_plan, next_attempt_at, updated_at);
