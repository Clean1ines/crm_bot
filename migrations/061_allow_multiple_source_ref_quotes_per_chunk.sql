-- Allow one canonical entry to keep multiple grounded evidence quotes
-- from the same source chunk.
--
-- This migration belongs to the retired legacy knowledge_entries /
-- knowledge_entry_source_refs schema. On fresh Workbench-only databases the
-- base table is intentionally absent, so this migration must be a no-op there.

DO $$
BEGIN
    IF to_regclass('public.knowledge_entry_source_refs') IS NULL THEN
        RAISE NOTICE 'Skipping 061_allow_multiple_source_ref_quotes_per_chunk: retired legacy table knowledge_entry_source_refs does not exist';
        RETURN;
    END IF;

    ALTER TABLE knowledge_entry_source_refs
        ADD COLUMN IF NOT EXISTS quote_hash TEXT;

    UPDATE knowledge_entry_source_refs
    SET quote_hash = md5(coalesce(quote, ''))
    WHERE quote_hash IS NULL;

    ALTER TABLE knowledge_entry_source_refs
        ALTER COLUMN quote_hash SET NOT NULL;

    ALTER TABLE knowledge_entry_source_refs
        DROP CONSTRAINT IF EXISTS pk_knowledge_entry_source_refs;

    ALTER TABLE knowledge_entry_source_refs
        ADD CONSTRAINT pk_knowledge_entry_source_refs
        PRIMARY KEY (entry_id, source_chunk_id, source_index, quote_hash);

    CREATE INDEX IF NOT EXISTS idx_knowledge_entry_source_refs_entry
        ON knowledge_entry_source_refs(entry_id);

    ANALYZE knowledge_entry_source_refs;
END $$;
