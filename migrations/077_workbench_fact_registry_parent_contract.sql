BEGIN;

-- 077_workbench_fact_registry_parent_contract.sql
--
-- Purpose:
-- Complete the Workbench registry_id forward repair.
--
-- 076 moved child-side snapshot column names to the current code contract:
--   knowledge_workbench_registry_snapshots.registry_id
--
-- But the parent table still had:
--   knowledge_workbench_fact_registries.fact_registry_id
--
-- This leaves the FK as:
--   snapshots.registry_id -> fact_registries.fact_registry_id
--
-- Current repository/domain code expects the parent column to be registry_id.
-- This migration renames the parent column and recreates dependent FKs/indexes.

SET LOCAL lock_timeout = '10s';
SET LOCAL statement_timeout = '120s';

-- ---------------------------------------------------------------------------
-- 1. Drop child FKs that reference fact registries before renaming parent column.
-- ---------------------------------------------------------------------------

ALTER TABLE IF EXISTS public.knowledge_workbench_registry_snapshots
    DROP CONSTRAINT IF EXISTS knowledge_workbench_registry_snapshots_fact_registry_id_fkey;

ALTER TABLE IF EXISTS public.knowledge_workbench_registry_snapshots
    DROP CONSTRAINT IF EXISTS knowledge_workbench_registry_snapshots_registry_id_fkey;

ALTER TABLE IF EXISTS public.knowledge_workbench_canonical_facts
    DROP CONSTRAINT IF EXISTS knowledge_workbench_canonical_facts_fact_registry_id_fkey;

ALTER TABLE IF EXISTS public.knowledge_workbench_canonical_facts
    DROP CONSTRAINT IF EXISTS knowledge_workbench_canonical_facts_registry_id_fkey;

ALTER TABLE IF EXISTS public.knowledge_workbench_fact_triples
    DROP CONSTRAINT IF EXISTS knowledge_workbench_fact_triples_fact_registry_id_fkey;

ALTER TABLE IF EXISTS public.knowledge_workbench_fact_triples
    DROP CONSTRAINT IF EXISTS knowledge_workbench_fact_triples_registry_id_fkey;

ALTER TABLE IF EXISTS public.knowledge_workbench_fact_mentions
    DROP CONSTRAINT IF EXISTS knowledge_workbench_fact_mentions_fact_registry_id_fkey;

ALTER TABLE IF EXISTS public.knowledge_workbench_fact_mentions
    DROP CONSTRAINT IF EXISTS knowledge_workbench_fact_mentions_registry_id_fkey;

ALTER TABLE IF EXISTS public.knowledge_workbench_fact_relations
    DROP CONSTRAINT IF EXISTS knowledge_workbench_fact_relations_fact_registry_id_fkey;

ALTER TABLE IF EXISTS public.knowledge_workbench_fact_relations
    DROP CONSTRAINT IF EXISTS knowledge_workbench_fact_relations_registry_id_fkey;

-- ---------------------------------------------------------------------------
-- 2. Rename parent registry column.
-- ---------------------------------------------------------------------------

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'knowledge_workbench_fact_registries'
          AND column_name = 'fact_registry_id'
    )
    AND NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'knowledge_workbench_fact_registries'
          AND column_name = 'registry_id'
    ) THEN
        ALTER TABLE public.knowledge_workbench_fact_registries
            RENAME COLUMN fact_registry_id TO registry_id;
    END IF;
END $$;

ALTER TABLE public.knowledge_workbench_fact_registries
    ALTER COLUMN registry_id SET NOT NULL;

-- Rename primary key constraint if it still has the old name.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'knowledge_workbench_fact_registries_pkey'
          AND conrelid = 'public.knowledge_workbench_fact_registries'::regclass
    ) THEN
        -- Keep default pkey name. No-op intentionally.
        NULL;
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 3. Rename child columns in first-class fact tables if they still use old names.
--    This aligns observability/runtime/debug paths with current registry_id naming.
-- ---------------------------------------------------------------------------

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'knowledge_workbench_canonical_facts'
          AND column_name = 'fact_registry_id'
    )
    AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'knowledge_workbench_canonical_facts'
          AND column_name = 'registry_id'
    ) THEN
        ALTER TABLE public.knowledge_workbench_canonical_facts
            RENAME COLUMN fact_registry_id TO registry_id;
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'knowledge_workbench_fact_triples'
          AND column_name = 'fact_registry_id'
    )
    AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'knowledge_workbench_fact_triples'
          AND column_name = 'registry_id'
    ) THEN
        ALTER TABLE public.knowledge_workbench_fact_triples
            RENAME COLUMN fact_registry_id TO registry_id;
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'knowledge_workbench_fact_mentions'
          AND column_name = 'fact_registry_id'
    )
    AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'knowledge_workbench_fact_mentions'
          AND column_name = 'registry_id'
    ) THEN
        ALTER TABLE public.knowledge_workbench_fact_mentions
            RENAME COLUMN fact_registry_id TO registry_id;
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'knowledge_workbench_fact_relations'
          AND column_name = 'fact_registry_id'
    )
    AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'knowledge_workbench_fact_relations'
          AND column_name = 'registry_id'
    ) THEN
        ALTER TABLE public.knowledge_workbench_fact_relations
            RENAME COLUMN fact_registry_id TO registry_id;
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- 4. Recreate canonical FKs against fact_registries.registry_id.
-- ---------------------------------------------------------------------------

ALTER TABLE public.knowledge_workbench_registry_snapshots
    ADD CONSTRAINT knowledge_workbench_registry_snapshots_registry_id_fkey
    FOREIGN KEY (registry_id)
    REFERENCES public.knowledge_workbench_fact_registries(registry_id)
    ON DELETE CASCADE;

ALTER TABLE public.knowledge_workbench_canonical_facts
    ADD CONSTRAINT knowledge_workbench_canonical_facts_registry_id_fkey
    FOREIGN KEY (registry_id)
    REFERENCES public.knowledge_workbench_fact_registries(registry_id)
    ON DELETE CASCADE;

ALTER TABLE public.knowledge_workbench_fact_triples
    ADD CONSTRAINT knowledge_workbench_fact_triples_registry_id_fkey
    FOREIGN KEY (registry_id)
    REFERENCES public.knowledge_workbench_fact_registries(registry_id)
    ON DELETE CASCADE;

ALTER TABLE public.knowledge_workbench_fact_mentions
    ADD CONSTRAINT knowledge_workbench_fact_mentions_registry_id_fkey
    FOREIGN KEY (registry_id)
    REFERENCES public.knowledge_workbench_fact_registries(registry_id)
    ON DELETE CASCADE;

ALTER TABLE public.knowledge_workbench_fact_relations
    ADD CONSTRAINT knowledge_workbench_fact_relations_registry_id_fkey
    FOREIGN KEY (registry_id)
    REFERENCES public.knowledge_workbench_fact_registries(registry_id)
    ON DELETE CASCADE;

-- ---------------------------------------------------------------------------
-- 5. Canonical indexes.
-- ---------------------------------------------------------------------------

DROP INDEX IF EXISTS public.idx_kwb_fact_registries_document;
DROP INDEX IF EXISTS public.idx_kwb_fact_registries_retention;
DROP INDEX IF EXISTS public.idx_kwb_canonical_facts_registry_status;

CREATE INDEX IF NOT EXISTS idx_kwb_fact_registries_document
    ON public.knowledge_workbench_fact_registries (
        project_id,
        document_id,
        processing_run_id,
        version DESC
    );

CREATE INDEX IF NOT EXISTS idx_kwb_fact_registries_retention
    ON public.knowledge_workbench_fact_registries (
        project_id,
        document_id,
        retention_state
    );

CREATE INDEX IF NOT EXISTS idx_kwb_canonical_facts_registry_status
    ON public.knowledge_workbench_canonical_facts (
        registry_id,
        status
    );

CREATE INDEX IF NOT EXISTS idx_kwb_fact_triples_registry
    ON public.knowledge_workbench_fact_triples (
        registry_id
    );

CREATE INDEX IF NOT EXISTS idx_kwb_fact_mentions_registry
    ON public.knowledge_workbench_fact_mentions (
        registry_id
    );

CREATE INDEX IF NOT EXISTS idx_kwb_fact_relations_registry
    ON public.knowledge_workbench_fact_relations (
        registry_id
    );

-- ---------------------------------------------------------------------------
-- 6. Postflight.
-- ---------------------------------------------------------------------------

DO $$
DECLARE
    missing_items TEXT[];
    legacy_items TEXT[];
BEGIN
    missing_items := ARRAY[]::TEXT[];
    legacy_items := ARRAY[]::TEXT[];

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'knowledge_workbench_fact_registries'
          AND column_name = 'registry_id'
    ) THEN
        missing_items := array_append(
            missing_items,
            'knowledge_workbench_fact_registries.registry_id'
        );
    END IF;

    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'knowledge_workbench_fact_registries'
          AND column_name = 'fact_registry_id'
    ) THEN
        legacy_items := array_append(
            legacy_items,
            'knowledge_workbench_fact_registries.fact_registry_id'
        );
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage ccu
          ON ccu.constraint_name = tc.constraint_name
         AND ccu.table_schema = tc.table_schema
        WHERE tc.table_schema = 'public'
          AND tc.table_name = 'knowledge_workbench_registry_snapshots'
          AND tc.constraint_type = 'FOREIGN KEY'
          AND kcu.column_name = 'registry_id'
          AND ccu.table_name = 'knowledge_workbench_fact_registries'
          AND ccu.column_name = 'registry_id'
    ) THEN
        missing_items := array_append(
            missing_items,
            'FK snapshots.registry_id -> fact_registries.registry_id'
        );
    END IF;

    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'knowledge_workbench_canonical_facts'
          AND column_name = 'fact_registry_id'
    ) THEN
        legacy_items := array_append(
            legacy_items,
            'knowledge_workbench_canonical_facts.fact_registry_id'
        );
    END IF;

    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'knowledge_workbench_fact_triples'
          AND column_name = 'fact_registry_id'
    ) THEN
        legacy_items := array_append(
            legacy_items,
            'knowledge_workbench_fact_triples.fact_registry_id'
        );
    END IF;

    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'knowledge_workbench_fact_mentions'
          AND column_name = 'fact_registry_id'
    ) THEN
        legacy_items := array_append(
            legacy_items,
            'knowledge_workbench_fact_mentions.fact_registry_id'
        );
    END IF;

    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'knowledge_workbench_fact_relations'
          AND column_name = 'fact_registry_id'
    ) THEN
        legacy_items := array_append(
            legacy_items,
            'knowledge_workbench_fact_relations.fact_registry_id'
        );
    END IF;

    IF array_length(missing_items, 1) IS NOT NULL THEN
        RAISE EXCEPTION
            'Workbench fact registry parent contract repair failed. Missing: %',
            array_to_string(missing_items, ', ');
    END IF;

    IF array_length(legacy_items, 1) IS NOT NULL THEN
        RAISE EXCEPTION
            'Workbench fact registry parent contract repair failed. Legacy still present: %',
            array_to_string(legacy_items, ', ');
    END IF;
END $$;

COMMIT;
