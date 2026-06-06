-- Workbench processing run active timer window.
--
-- current_active_started_at is the start of the current active processing
-- window. active_elapsed_seconds stores accumulated active time before the
-- current active window.

ALTER TABLE knowledge_workbench_processing_runs
ADD COLUMN IF NOT EXISTS current_active_started_at TIMESTAMPTZ NULL;

UPDATE knowledge_workbench_processing_runs
SET current_active_started_at = COALESCE(current_active_started_at, started_at)
WHERE status = 'running'
  AND current_active_started_at IS NULL;
