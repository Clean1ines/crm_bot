-- Migration 056: Replace legacy knowledge entry_type with canonical entry_kind.
--
-- KCD v1 PHASE 4 / Batch 3 breaking cut:
-- - preprocessing_mode remains document/compiler strategy;
-- - knowledge_base.entry_kind stores canonical KnowledgeEntryKind values only;
-- - legacy values chunk/answer_knowledge/faq/price_list/instruction are removed
--   from runtime storage semantics.

DROP INDEX IF EXISTS idx_knowledge_base_document_entry_type;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'knowledge_base'
          AND column_name = 'entry_type'
    )
    AND NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'knowledge_base'
          AND column_name = 'entry_kind'
    )
    THEN
        ALTER TABLE knowledge_base RENAME COLUMN entry_type TO entry_kind;
    END IF;
END $$;

ALTER TABLE knowledge_base
    ADD COLUMN IF NOT EXISTS entry_kind TEXT NOT NULL DEFAULT 'answer';

UPDATE knowledge_base
SET entry_kind = CASE entry_kind
    WHEN 'chunk' THEN 'answer'
    WHEN 'answer_knowledge' THEN 'answer'
    WHEN 'faq' THEN 'faq_answer'
    WHEN 'price_list' THEN 'price_answer'
    WHEN 'instruction' THEN 'procedure'
    WHEN 'retrieval_guideline' THEN 'custom'
    WHEN 'internal_eval_test' THEN 'custom'
    WHEN 'negative_test' THEN 'custom'
    ELSE entry_kind
END;

ALTER TABLE knowledge_base
    ALTER COLUMN entry_kind SET DEFAULT 'answer';

ALTER TABLE knowledge_base
    DROP CONSTRAINT IF EXISTS chk_knowledge_base_entry_kind;

ALTER TABLE knowledge_base
    ADD CONSTRAINT chk_knowledge_base_entry_kind CHECK (
        entry_kind IN (
            'answer',
            'faq_answer',
            'contact_info',
            'working_hours',
            'catalog_answer',
            'price_answer',
            'pricing_policy',
            'refund_policy',
            'delivery_policy',
            'policy_clause',
            'procedure',
            'warning',
            'requirement',
            'troubleshooting_step',
            'custom'
        )
    );

CREATE INDEX IF NOT EXISTS idx_knowledge_base_document_entry_kind
    ON knowledge_base(document_id, entry_kind);

DROP INDEX IF EXISTS your_index_name;

ANALYZE knowledge_base;
