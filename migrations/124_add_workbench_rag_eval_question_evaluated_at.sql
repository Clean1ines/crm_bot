ALTER TABLE knowledge_workbench_rag_eval_questions
    ADD COLUMN IF NOT EXISTS evaluated_at TIMESTAMPTZ NULL;

CREATE INDEX IF NOT EXISTS idx_kwb_rag_eval_questions_evaluated_at
    ON knowledge_workbench_rag_eval_questions(run_id, evaluated_at)
    WHERE evaluated_at IS NOT NULL;
