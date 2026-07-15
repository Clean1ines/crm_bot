ALTER TABLE knowledge_workbench_rag_eval_questions
    DROP CONSTRAINT IF EXISTS chk_kwb_rag_eval_question_kind;

ALTER TABLE knowledge_workbench_rag_eval_questions
    ADD CONSTRAINT chk_kwb_rag_eval_question_kind
    CHECK (
        question_kind IN (
            'direct_paraphrase',
            'lexical_variant',
            'naive_user',
            'entity_first',
            'action_first',
            'constraint_first',
            'domain_specific',
            'existing_possible_question',
            'paraphrase',
            'synonym',
            'naive_user_question'
        )
    );
