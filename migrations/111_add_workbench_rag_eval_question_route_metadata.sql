ALTER TABLE knowledge_workbench_rag_eval_questions
    ADD COLUMN IF NOT EXISTS generation_account_ref text,
    ADD COLUMN IF NOT EXISTS generation_slot_index integer;

CREATE INDEX IF NOT EXISTS idx_workbench_rag_eval_questions_generation_route
    ON knowledge_workbench_rag_eval_questions (
        project_id,
        run_id,
        generation_model,
        generation_account_ref,
        generation_slot_index
    );
