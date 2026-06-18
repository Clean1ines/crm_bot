-- Phase 14.1
-- Allow Workbench canonical facts to be projected into the retired legacy
-- vector+FTS retrieval surface via knowledge_entries/knowledge_retrieval_surface.
--
-- Fresh Workbench-only databases intentionally do not create this retired legacy
-- schema, so this migration must be a no-op when those tables are absent.

DO $$
BEGIN
    IF to_regclass('public.knowledge_entries') IS NULL THEN
        RAISE NOTICE 'Skipping 079_add_faq_workbench_fact_runtime_entry_kind: retired legacy table knowledge_entries does not exist';
        RETURN;
    END IF;

    IF to_regclass('public.knowledge_retrieval_surface') IS NULL THEN
        RAISE NOTICE 'Skipping 079_add_faq_workbench_fact_runtime_entry_kind: retired legacy table knowledge_retrieval_surface does not exist';
        RETURN;
    END IF;

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
END $$;
