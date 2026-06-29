ALTER TABLE public.execution_queue
ADD COLUMN IF NOT EXISTS next_attempt_at timestamptz NULL;

CREATE INDEX IF NOT EXISTS idx_queue_status_next_attempt_at
ON public.execution_queue(status, next_attempt_at, created_at);
