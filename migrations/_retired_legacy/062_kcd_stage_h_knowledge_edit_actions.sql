-- Migration 062: KCD v1 Stage H knowledge edit actions.
--
-- Stage H target:
-- - Persist executable KnowledgeEditAction audit trail.
-- - Record entry version snapshots for applied mutations.
-- - Keep knowledge_entries as source of truth.
-- - Keep knowledge_retrieval_surface as rebuildable runtime projection.
-- - Execute only safe actions automatically:
--   attach_question_to_entry, rebuild_embedding, rerun_eval.
-- - create_entry_from_failure remains audit/review-only until explicit editor UX.

BEGIN;

CREATE TABLE IF NOT EXISTS knowledge_edit_actions (
    id TEXT PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    document_id UUID REFERENCES knowledge_documents(id) ON DELETE CASCADE,
    source_result_id TEXT REFERENCES rag_eval_results(id) ON DELETE SET NULL,
    source_run_id TEXT REFERENCES rag_eval_runs(id) ON DELETE SET NULL,
    source_question_id TEXT REFERENCES rag_eval_questions(id) ON DELETE SET NULL,
    action_index INTEGER NOT NULL DEFAULT 0,
    actor_user_id TEXT NOT NULL DEFAULT '',
    action_type TEXT NOT NULL,
    target_entry_id UUID REFERENCES knowledge_entries(id) ON DELETE SET NULL,
    reason TEXT NOT NULL DEFAULT '',
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    result_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'proposed',
    error TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    applied_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ck_knowledge_edit_actions_id_not_blank
        CHECK (btrim(id) <> ''),
    CONSTRAINT ck_knowledge_edit_actions_action_index_non_negative
        CHECK (action_index >= 0),
    CONSTRAINT ck_knowledge_edit_actions_action_type
        CHECK (
            action_type IN (
                'attach_question_to_entry',
                'create_entry_from_failure',
                'rebuild_embedding',
                'rerun_eval'
            )
        ),
    CONSTRAINT ck_knowledge_edit_actions_status
        CHECK (
            status IN (
                'proposed',
                'applied',
                'rejected',
                'failed'
            )
        ),
    CONSTRAINT ck_knowledge_edit_actions_payload_object
        CHECK (jsonb_typeof(payload) = 'object'),
    CONSTRAINT ck_knowledge_edit_actions_result_payload_object
        CHECK (jsonb_typeof(result_payload) = 'object')
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_knowledge_edit_actions_source_result_index
    ON knowledge_edit_actions(source_result_id, action_index)
    WHERE source_result_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_knowledge_edit_actions_project_document
    ON knowledge_edit_actions(project_id, document_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_knowledge_edit_actions_target_entry
    ON knowledge_edit_actions(target_entry_id, created_at DESC)
    WHERE target_entry_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_knowledge_edit_actions_status
    ON knowledge_edit_actions(status, created_at DESC);

CREATE TABLE IF NOT EXISTS knowledge_entry_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entry_id UUID NOT NULL REFERENCES knowledge_entries(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    document_id UUID REFERENCES knowledge_documents(id) ON DELETE CASCADE,
    action_id TEXT REFERENCES knowledge_edit_actions(id) ON DELETE SET NULL,
    from_version INTEGER NOT NULL,
    to_version INTEGER NOT NULL,
    previous_snapshot JSONB NOT NULL,
    new_snapshot JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ck_knowledge_entry_versions_positive
        CHECK (from_version >= 1 AND to_version >= 1),
    CONSTRAINT ck_knowledge_entry_versions_monotonic
        CHECK (to_version >= from_version),
    CONSTRAINT ck_knowledge_entry_versions_previous_object
        CHECK (jsonb_typeof(previous_snapshot) = 'object'),
    CONSTRAINT ck_knowledge_entry_versions_new_object
        CHECK (jsonb_typeof(new_snapshot) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_knowledge_entry_versions_entry_created
    ON knowledge_entry_versions(entry_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_knowledge_entry_versions_action
    ON knowledge_entry_versions(action_id)
    WHERE action_id IS NOT NULL;

COMMENT ON TABLE knowledge_edit_actions IS
    'KCD Stage H executable/audited KnowledgeEditAction records derived from RAG eval failures.';

COMMENT ON TABLE knowledge_entry_versions IS
    'KCD Stage H immutable snapshots of knowledge_entries around applied edit actions.';

ANALYZE knowledge_edit_actions;
ANALYZE knowledge_entry_versions;

COMMIT;
