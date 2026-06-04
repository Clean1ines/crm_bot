BEGIN;

-- 076_workbench_schema_contract_forward_repair.sql
--
-- Purpose:
-- Bring already-applied FAQ Workbench production schema forward to the
-- current code contract without editing historical migrations.
--
-- Fixes confirmed drift:
-- 1. knowledge_workbench_registry_snapshots:
--    fact_registry_id      -> registry_id
--    fact_registry_payload -> entries_payload
--    canonical_fact_count  -> entry_count
--    fact_relation_count   -> relation_count
--    + relations_payload
--
-- 2. knowledge_workbench_fact_registry_application_queue:
--    fact_registry_node_run_id -> source_node_run_id
--
-- 3. knowledge_workbench_section_batch_queue_items:
--    fact_registry_application_queue_item_id -> registry_application_queue_item_id
--
-- 4. Missing current-code table:
--    knowledge_workbench_registry_update_applications
--
-- 5. Error/cancel paths:
--    knowledge_workbench_processing_runs.last_error

SET LOCAL lock_timeout = '10s';
SET LOCAL statement_timeout = '120s';

-- ---------------------------------------------------------------------------
-- 1. Registry snapshots: forward column names to current repository contract.
-- ---------------------------------------------------------------------------

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'knowledge_workbench_registry_snapshots'
          AND column_name = 'fact_registry_id'
    )
    AND NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'knowledge_workbench_registry_snapshots'
          AND column_name = 'registry_id'
    ) THEN
        ALTER TABLE public.knowledge_workbench_registry_snapshots
            RENAME COLUMN fact_registry_id TO registry_id;
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'knowledge_workbench_registry_snapshots'
          AND column_name = 'fact_registry_payload'
    )
    AND NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'knowledge_workbench_registry_snapshots'
          AND column_name = 'entries_payload'
    ) THEN
        ALTER TABLE public.knowledge_workbench_registry_snapshots
            RENAME COLUMN fact_registry_payload TO entries_payload;
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'knowledge_workbench_registry_snapshots'
          AND column_name = 'canonical_fact_count'
    )
    AND NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'knowledge_workbench_registry_snapshots'
          AND column_name = 'entry_count'
    ) THEN
        ALTER TABLE public.knowledge_workbench_registry_snapshots
            RENAME COLUMN canonical_fact_count TO entry_count;
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'knowledge_workbench_registry_snapshots'
          AND column_name = 'fact_relation_count'
    )
    AND NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'knowledge_workbench_registry_snapshots'
          AND column_name = 'relation_count'
    ) THEN
        ALTER TABLE public.knowledge_workbench_registry_snapshots
            RENAME COLUMN fact_relation_count TO relation_count;
    END IF;
END $$;

ALTER TABLE public.knowledge_workbench_registry_snapshots
    ADD COLUMN IF NOT EXISTS relations_payload JSONB NOT NULL DEFAULT '{"relations":[]}'::jsonb;

-- Defensive backfill for databases where entries_payload was added manually
-- instead of renamed from fact_registry_payload.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'knowledge_workbench_registry_snapshots'
          AND column_name = 'entries_payload'
    )
    AND EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'knowledge_workbench_registry_snapshots'
          AND column_name = 'fact_registry_payload'
    ) THEN
        UPDATE public.knowledge_workbench_registry_snapshots
        SET entries_payload = fact_registry_payload
        WHERE entries_payload IS NULL
           OR entries_payload = '{}'::jsonb;
    END IF;
END $$;

UPDATE public.knowledge_workbench_registry_snapshots
SET relations_payload = '{"relations":[]}'::jsonb
WHERE relations_payload IS NULL;

-- Current repository expects these names and non-null values.
ALTER TABLE public.knowledge_workbench_registry_snapshots
    ALTER COLUMN registry_id SET NOT NULL,
    ALTER COLUMN entries_payload SET DEFAULT '{}'::jsonb,
    ALTER COLUMN entries_payload SET NOT NULL,
    ALTER COLUMN relations_payload SET DEFAULT '{"relations":[]}'::jsonb,
    ALTER COLUMN relations_payload SET NOT NULL,
    ALTER COLUMN entry_count SET DEFAULT 0,
    ALTER COLUMN entry_count SET NOT NULL,
    ALTER COLUMN relation_count SET DEFAULT 0,
    ALTER COLUMN relation_count SET NOT NULL;

-- Keep the old index name if PostgreSQL preserved it through column rename;
-- add canonical index names used for future schema checks.
CREATE INDEX IF NOT EXISTS idx_kwb_registry_snapshots_latest
    ON public.knowledge_workbench_registry_snapshots (
        project_id,
        document_id,
        processing_run_id,
        sequence_number DESC
    );

CREATE INDEX IF NOT EXISTS idx_kwb_registry_snapshots_published
    ON public.knowledge_workbench_registry_snapshots (
        project_id,
        document_id,
        is_final_published
    )
    WHERE is_final_published IS TRUE;

-- ---------------------------------------------------------------------------
-- 2. Registry application queue: forward source node column name.
-- ---------------------------------------------------------------------------

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'knowledge_workbench_fact_registry_application_queue'
          AND column_name = 'fact_registry_node_run_id'
    )
    AND NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'knowledge_workbench_fact_registry_application_queue'
          AND column_name = 'source_node_run_id'
    ) THEN
        ALTER TABLE public.knowledge_workbench_fact_registry_application_queue
            RENAME COLUMN fact_registry_node_run_id TO source_node_run_id;
    END IF;
END $$;

ALTER TABLE public.knowledge_workbench_fact_registry_application_queue
    ALTER COLUMN source_node_run_id SET NOT NULL;

CREATE INDEX IF NOT EXISTS idx_workbench_fact_registry_application_queue_source_node
    ON public.knowledge_workbench_fact_registry_application_queue (
        project_id,
        document_id,
        processing_run_id,
        source_node_run_id
    );

-- ---------------------------------------------------------------------------
-- 3. Section batch queue: forward registry application queue ref column name.
-- ---------------------------------------------------------------------------

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'knowledge_workbench_section_batch_queue_items'
          AND column_name = 'fact_registry_application_queue_item_id'
    )
    AND NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'knowledge_workbench_section_batch_queue_items'
          AND column_name = 'registry_application_queue_item_id'
    ) THEN
        ALTER TABLE public.knowledge_workbench_section_batch_queue_items
            RENAME COLUMN fact_registry_application_queue_item_id TO registry_application_queue_item_id;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_workbench_section_batch_queue_registry_application
    ON public.knowledge_workbench_section_batch_queue_items (
        project_id,
        document_id,
        processing_run_id,
        registry_application_queue_item_id
    )
    WHERE registry_application_queue_item_id IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 4. Missing current-code table:
--    knowledge_workbench_registry_update_applications.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.knowledge_workbench_registry_update_applications (
    application_id TEXT PRIMARY KEY,
    processing_run_id TEXT NOT NULL
        REFERENCES public.knowledge_workbench_processing_runs(processing_run_id)
        ON DELETE CASCADE,
    project_id UUID NOT NULL
        REFERENCES public.projects(id)
        ON DELETE CASCADE,
    document_id TEXT NOT NULL
        REFERENCES public.knowledge_workbench_documents(document_id)
        ON DELETE CASCADE,
    section_id TEXT
        REFERENCES public.knowledge_workbench_document_sections(section_id)
        ON DELETE SET NULL,
    proposal_id TEXT,
    applied_by TEXT NOT NULL,
    operation TEXT NOT NULL,
    target_fact_id TEXT,
    before_snapshot_id TEXT
        REFERENCES public.knowledge_workbench_registry_snapshots(snapshot_id)
        ON DELETE SET NULL,
    after_snapshot_id TEXT
        REFERENCES public.knowledge_workbench_registry_snapshots(snapshot_id)
        ON DELETE SET NULL,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_kwb_registry_update_applications_run
    ON public.knowledge_workbench_registry_update_applications (
        project_id,
        document_id,
        processing_run_id,
        applied_at
    );

CREATE INDEX IF NOT EXISTS idx_kwb_registry_update_applications_section
    ON public.knowledge_workbench_registry_update_applications (
        project_id,
        document_id,
        section_id
    )
    WHERE section_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_kwb_registry_update_applications_snapshots
    ON public.knowledge_workbench_registry_update_applications (
        before_snapshot_id,
        after_snapshot_id
    );

CREATE INDEX IF NOT EXISTS idx_kwb_registry_update_applications_target_fact
    ON public.knowledge_workbench_registry_update_applications (
        target_fact_id
    )
    WHERE target_fact_id IS NOT NULL;

-- ---------------------------------------------------------------------------
-- 5. Error/cancel path compatibility with current repository.
-- ---------------------------------------------------------------------------

ALTER TABLE public.knowledge_workbench_processing_runs
    ADD COLUMN IF NOT EXISTS last_error TEXT;

-- ---------------------------------------------------------------------------
-- 6. Explicit schema-contract postflight.
--    Fail the migration if the DB still does not match the current code.
-- ---------------------------------------------------------------------------

DO $$
DECLARE
    missing_items TEXT[];
BEGIN
    missing_items := ARRAY[]::TEXT[];

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'knowledge_workbench_registry_snapshots'
          AND column_name = 'registry_id'
    ) THEN
        missing_items := array_append(missing_items, 'knowledge_workbench_registry_snapshots.registry_id');
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'knowledge_workbench_registry_snapshots'
          AND column_name = 'entries_payload'
    ) THEN
        missing_items := array_append(missing_items, 'knowledge_workbench_registry_snapshots.entries_payload');
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'knowledge_workbench_registry_snapshots'
          AND column_name = 'relations_payload'
    ) THEN
        missing_items := array_append(missing_items, 'knowledge_workbench_registry_snapshots.relations_payload');
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'knowledge_workbench_registry_snapshots'
          AND column_name = 'entry_count'
    ) THEN
        missing_items := array_append(missing_items, 'knowledge_workbench_registry_snapshots.entry_count');
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'knowledge_workbench_registry_snapshots'
          AND column_name = 'relation_count'
    ) THEN
        missing_items := array_append(missing_items, 'knowledge_workbench_registry_snapshots.relation_count');
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'knowledge_workbench_fact_registry_application_queue'
          AND column_name = 'source_node_run_id'
    ) THEN
        missing_items := array_append(missing_items, 'knowledge_workbench_fact_registry_application_queue.source_node_run_id');
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'knowledge_workbench_section_batch_queue_items'
          AND column_name = 'registry_application_queue_item_id'
    ) THEN
        missing_items := array_append(missing_items, 'knowledge_workbench_section_batch_queue_items.registry_application_queue_item_id');
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name = 'knowledge_workbench_registry_update_applications'
    ) THEN
        missing_items := array_append(missing_items, 'knowledge_workbench_registry_update_applications');
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'knowledge_workbench_processing_runs'
          AND column_name = 'last_error'
    ) THEN
        missing_items := array_append(missing_items, 'knowledge_workbench_processing_runs.last_error');
    END IF;

    IF array_length(missing_items, 1) IS NOT NULL THEN
        RAISE EXCEPTION
            'Workbench schema contract forward repair failed. Missing: %',
            array_to_string(missing_items, ', ');
    END IF;
END $$;

COMMIT;
