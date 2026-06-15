ALTER TABLE draft_claim_compaction_nodes
    ADD COLUMN IF NOT EXISTS compacted_claim_kind text NULL,
    ADD COLUMN IF NOT EXISTS compacted_granularity text NULL,
    ADD COLUMN IF NOT EXISTS compacted_merge_decision text NULL,
    ADD COLUMN IF NOT EXISTS compacted_payload jsonb NULL;
