-- Migration 065: Knowledge Curation / Compilation Review Console support.
-- Extends canonical entry and KnowledgeEditAction vocabularies for manual curation.

BEGIN;

ALTER TABLE knowledge_entries
    DROP CONSTRAINT IF EXISTS ck_knowledge_entries_status;

ALTER TABLE knowledge_entries
    ADD CONSTRAINT ck_knowledge_entries_status CHECK (
        status IN (
            'draft',
            'grounded',
            'enriched',
            'embedded',
            'published',
            'needs_review',
            'hidden',
            'archived',
            'rejected',
            'merged'
        )
    );

ALTER TABLE knowledge_edit_actions
    ADD COLUMN IF NOT EXISTS source_kind TEXT NOT NULL DEFAULT 'rag_eval',
    ADD COLUMN IF NOT EXISTS source_id TEXT,
    ADD COLUMN IF NOT EXISTS idempotency_key TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS target_entry_ids_json JSONB NOT NULL DEFAULT '[]'::jsonb;

UPDATE knowledge_edit_actions
SET source_kind = 'rag_eval'
WHERE source_kind = '' OR source_kind IS NULL;

ALTER TABLE knowledge_edit_actions
    DROP CONSTRAINT IF EXISTS ck_knowledge_edit_actions_action_type;

ALTER TABLE knowledge_edit_actions
    ADD CONSTRAINT ck_knowledge_edit_actions_action_type CHECK (
        action_type IN (
            'attach_question_to_entry',
            'create_entry_from_failure',
            'rebuild_embedding',
            'rerun_eval',
            'merge_entries',
            'hide_entry',
            'reject_entry',
            'restore_entry',
            'publish_entry',
            'unpublish_entry',
            'edit_entry_title',
            'edit_entry_answer',
            'edit_entry_enrichment'
        )
    );

ALTER TABLE knowledge_edit_actions
    DROP CONSTRAINT IF EXISTS ck_knowledge_edit_actions_status;

ALTER TABLE knowledge_edit_actions
    ADD CONSTRAINT ck_knowledge_edit_actions_status CHECK (
        status IN ('proposed', 'applied', 'rejected', 'failed', 'applied_with_warning')
    );

ALTER TABLE knowledge_edit_actions
    DROP CONSTRAINT IF EXISTS ck_knowledge_edit_actions_source_kind_not_blank;

ALTER TABLE knowledge_edit_actions
    ADD CONSTRAINT ck_knowledge_edit_actions_source_kind_not_blank CHECK (btrim(source_kind) <> '');

ALTER TABLE knowledge_edit_actions
    DROP CONSTRAINT IF EXISTS ck_knowledge_edit_actions_target_entry_ids_array;

ALTER TABLE knowledge_edit_actions
    ADD CONSTRAINT ck_knowledge_edit_actions_target_entry_ids_array CHECK (jsonb_typeof(target_entry_ids_json) = 'array');

CREATE UNIQUE INDEX IF NOT EXISTS uq_knowledge_edit_actions_curation_idempotency
    ON knowledge_edit_actions(project_id, document_id, source_kind, idempotency_key)
    WHERE idempotency_key <> '';

CREATE INDEX IF NOT EXISTS idx_knowledge_edit_actions_project_document_source
    ON knowledge_edit_actions(project_id, document_id, source_kind, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_knowledge_entries_curation_document_status
    ON knowledge_entries(project_id, document_id, status, visibility, updated_at DESC);

ANALYZE knowledge_entries;
ANALYZE knowledge_edit_actions;

COMMIT;
