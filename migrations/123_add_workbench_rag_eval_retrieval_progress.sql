ALTER TABLE knowledge_workbench_rag_eval_runs
    ADD COLUMN IF NOT EXISTS retrieval_total_questions INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS retrieval_evaluated_questions INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS retrieval_pass_strong INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS retrieval_pass_weak INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS retrieval_confusions INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS retrieval_misses INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS retrieval_existing_alias_failures INTEGER NOT NULL DEFAULT 0;

ALTER TABLE knowledge_workbench_rag_eval_runs
    ADD CONSTRAINT chk_kwb_rag_eval_retrieval_progress_non_negative
    CHECK (
        retrieval_total_questions >= 0
        AND retrieval_evaluated_questions >= 0
        AND retrieval_pass_strong >= 0
        AND retrieval_pass_weak >= 0
        AND retrieval_confusions >= 0
        AND retrieval_misses >= 0
        AND retrieval_existing_alias_failures >= 0
    );
