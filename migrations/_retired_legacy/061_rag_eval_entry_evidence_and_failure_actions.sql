-- Migration 061: realign RAG eval evidence to canonical entries.
--
-- Stage G:
-- - Eval evidence primary identity is entry_id, not chunk_id.
-- - source_chunk_id remains valid only inside source refs as raw source evidence.
-- - FailureClassification and proposed KnowledgeEditAction values become first-class result fields.
-- - No edit actions are executed by this migration.

BEGIN;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'rag_eval_questions'
          AND column_name = 'expected_chunk_ids'
    )
    AND NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'rag_eval_questions'
          AND column_name = 'expected_entry_ids'
    ) THEN
        ALTER TABLE rag_eval_questions
            RENAME COLUMN expected_chunk_ids TO expected_entry_ids;
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'rag_eval_results'
          AND column_name = 'retrieved_chunk_ids'
    )
    AND NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'rag_eval_results'
          AND column_name = 'retrieved_entry_ids'
    ) THEN
        ALTER TABLE rag_eval_results
            RENAME COLUMN retrieved_chunk_ids TO retrieved_entry_ids;
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'rag_eval_results'
          AND column_name = 'expected_chunk_found'
    )
    AND NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'rag_eval_results'
          AND column_name = 'expected_entry_found'
    ) THEN
        ALTER TABLE rag_eval_results
            RENAME COLUMN expected_chunk_found TO expected_entry_found;
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'rag_eval_results'
          AND column_name = 'wrong_chunk_top1'
    )
    AND NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'rag_eval_results'
          AND column_name = 'wrong_entry_top1'
    ) THEN
        ALTER TABLE rag_eval_results
            RENAME COLUMN wrong_chunk_top1 TO wrong_entry_top1;
    END IF;
END $$;

ALTER TABLE rag_eval_results
    ADD COLUMN IF NOT EXISTS classification JSONB,
    ADD COLUMN IF NOT EXISTS proposed_actions JSONB NOT NULL DEFAULT '[]'::jsonb;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_rag_eval_results_classification_object'
    ) THEN
        ALTER TABLE rag_eval_results
            ADD CONSTRAINT ck_rag_eval_results_classification_object
            CHECK (
                classification IS NULL
                OR jsonb_typeof(classification) = 'object'
            );
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_rag_eval_results_proposed_actions_array'
    ) THEN
        ALTER TABLE rag_eval_results
            ADD CONSTRAINT ck_rag_eval_results_proposed_actions_array
            CHECK (jsonb_typeof(proposed_actions) = 'array');
    END IF;
END $$;

COMMENT ON COLUMN rag_eval_questions.expected_entry_ids IS
    'Expected canonical knowledge entry ids for this eval case. Raw source evidence remains in source refs.';

COMMENT ON COLUMN rag_eval_results.retrieved_entry_ids IS
    'Retrieved canonical knowledge entry ids returned by production retrieval.';

COMMENT ON COLUMN rag_eval_results.classification IS
    'Typed FailureClassification payload for failed or degraded eval results.';

COMMENT ON COLUMN rag_eval_results.proposed_actions IS
    'Proposed KnowledgeEditAction payloads. These actions are suggestions only and are not executed by Stage G.';

COMMIT;
