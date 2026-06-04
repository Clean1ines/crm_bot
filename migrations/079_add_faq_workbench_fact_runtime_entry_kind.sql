BEGIN;

-- Phase 14.1
-- Allow Workbench canonical facts to be projected into the existing production
-- vector+FTS retrieval surface via knowledge_entries/knowledge_retrieval_surface.
--
-- This does not create a second runtime retrieval reality. It lets Workbench
-- publish canonical facts into the same runtime surface used by SearchKnowledgeTool.

ALTER TABLE knowledge_entries
    DROP CONSTRAINT IF EXISTS ck_knowledge_entries_entry_kind;

ALTER TABLE knowledge_entries
    ADD CONSTRAINT ck_knowledge_entries_entry_kind CHECK (
        entry_kind IN (
            'answer',
            'faq_answer',
            'faq_workbench_fact',
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
            'fallback_chunk',
            'custom'
        )
    );

CREATE INDEX IF NOT EXISTS idx_knowledge_entries_workbench_fact_runtime
    ON knowledge_entries(project_id, entry_kind, status, visibility)
    WHERE entry_kind = 'faq_workbench_fact';

CREATE INDEX IF NOT EXISTS idx_knowledge_retrieval_surface_workbench_fact_runtime
    ON knowledge_retrieval_surface(project_id, entry_kind, status, visibility)
    WHERE entry_kind = 'faq_workbench_fact';

COMMIT;
