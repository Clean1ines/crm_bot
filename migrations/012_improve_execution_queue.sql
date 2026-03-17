-- Migration: 012_improve_execution_queue
-- Purpose: Add reliability fields to execution queue
-- Enables retry logic, timeout handling, and worker tracking

ALTER TABLE execution_queue 
ADD COLUMN IF NOT EXISTS attempts INTEGER DEFAULT 0;

ALTER TABLE execution_queue 
ADD COLUMN IF NOT EXISTS max_attempts INTEGER DEFAULT 3;

ALTER TABLE execution_queue 
ADD COLUMN IF NOT EXISTS locked_at TIMESTAMP WITH TIME ZONE DEFAULT NULL;

ALTER TABLE execution_queue 
ADD COLUMN IF NOT EXISTS worker_id TEXT DEFAULT NULL;

ALTER TABLE execution_queue 
ADD COLUMN IF NOT EXISTS error TEXT DEFAULT NULL;

-- Index for locked jobs timeout detection
CREATE INDEX IF NOT EXISTS idx_queue_locked_at ON execution_queue(locked_at) 
WHERE locked_at IS NOT NULL AND status = 'processing';

-- Index for failed jobs
CREATE INDEX IF NOT EXISTS idx_queue_error ON execution_queue(status, error) 
WHERE status = 'failed';

-- Comment for documentation
COMMENT ON COLUMN execution_queue.attempts IS 'Number of processing attempts';
COMMENT ON COLUMN execution_queue.max_attempts IS 'Maximum attempts before permanent failure';
COMMENT ON COLUMN execution_queue.locked_at IS 'Timestamp when job was locked by worker';
COMMENT ON COLUMN execution_queue.worker_id IS 'Identifier of worker processing this job';
COMMENT ON COLUMN execution_queue.error IS 'Error message from last failed attempt';
