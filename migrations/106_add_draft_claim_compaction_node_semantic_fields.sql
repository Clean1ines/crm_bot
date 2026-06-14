ALTER TABLE draft_claim_compaction_nodes
    ADD COLUMN IF NOT EXISTS compacted_key text NULL,
    ADD COLUMN IF NOT EXISTS compacted_claim text NULL,
    ADD COLUMN IF NOT EXISTS compacted_triples jsonb NOT NULL DEFAULT '[]'::jsonb;
