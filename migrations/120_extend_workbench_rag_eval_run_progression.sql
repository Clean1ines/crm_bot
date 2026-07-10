ALTER TABLE knowledge_workbench_rag_eval_runs
    DROP CONSTRAINT IF EXISTS chk_kwb_rag_eval_run_status;

ALTER TABLE knowledge_workbench_rag_eval_runs
    ADD COLUMN IF NOT EXISTS current_phase TEXT NOT NULL DEFAULT 'scope_resolution',
    ADD COLUMN IF NOT EXISTS blocked_reason TEXT NULL,
    ADD COLUMN IF NOT EXISTS failed_reason TEXT NULL,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ADD COLUMN IF NOT EXISTS selected_entries INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS scheduled_generation_items INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS waiting_work_items INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS running_work_items INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS completed_work_items INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS failed_work_items INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS generated_question_sets INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS capacity_next_due_at TIMESTAMPTZ NULL,
    ADD COLUMN IF NOT EXISTS capacity_model_ref TEXT NULL,
    ADD COLUMN IF NOT EXISTS capacity_account_ref TEXT NULL;

UPDATE knowledge_workbench_rag_eval_runs
SET current_phase = CASE status
        WHEN 'created' THEN 'scope_resolution'
        WHEN 'completed' THEN 'completed'
        WHEN 'failed' THEN 'failed'
        ELSE 'question_generation'
    END,
    updated_at = COALESCE(completed_at, started_at, created_at),
    selected_entries = total_entries
WHERE current_phase = 'scope_resolution';

ALTER TABLE knowledge_workbench_rag_eval_runs
    ADD CONSTRAINT chk_kwb_rag_eval_run_status
        CHECK (status IN (
            'created', 'running', 'waiting_capacity', 'promotion_review',
            'verifying', 'completed', 'blocked', 'failed'
        )),
    ADD CONSTRAINT chk_kwb_rag_eval_run_current_phase
        CHECK (current_phase IN (
            'scope_resolution', 'question_generation_scheduling',
            'question_generation', 'retrieval_evaluation',
            'adjudication_scheduling', 'adjudication', 'promotion_review',
            'promotion_application', 'post_promotion_verification',
            'completed', 'blocked', 'failed'
        )),
    ADD CONSTRAINT chk_kwb_rag_eval_run_progress_non_negative
        CHECK (
            selected_entries >= 0
            AND scheduled_generation_items >= 0
            AND waiting_work_items >= 0
            AND running_work_items >= 0
            AND completed_work_items >= 0
            AND failed_work_items >= 0
            AND generated_question_sets >= 0
        );
