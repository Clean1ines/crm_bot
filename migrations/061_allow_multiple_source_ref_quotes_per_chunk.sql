-- Allow one canonical entry to keep multiple grounded evidence quotes
-- from the same source chunk.
--
-- Stage K.7 preserves per-semantic-entry source excerpts. A single canonical
-- answer may now legitimately have several quotes with the same
-- (entry_id, source_chunk_id, source_index). The quote itself must therefore
-- participate in source-ref identity.

BEGIN;

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

COMMIT;
