BEGIN;

CREATE TABLE IF NOT EXISTS knowledge_surface_candidates (
    id UUID PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES knowledge_surface_compiler_runs(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,
    source_unit_id UUID NOT NULL REFERENCES knowledge_surface_source_units(id) ON DELETE CASCADE,
    local_surface_key TEXT NOT NULL,
    provisional_title TEXT NOT NULL,
    surface_kind TEXT NOT NULL,
    answer_scope TEXT NOT NULL,
    question_scope TEXT NOT NULL,
    exclusion_scope TEXT NOT NULL,
    parent_candidate_keys JSONB NOT NULL DEFAULT '[]'::jsonb,
    child_candidate_keys JSONB NOT NULL DEFAULT '[]'::jsonb,
    sibling_candidate_keys JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (run_id, local_surface_key)
);

CREATE TABLE IF NOT EXISTS knowledge_surface_answer_drafts (
    id UUID PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES knowledge_surface_compiler_runs(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,
    candidate_key TEXT NOT NULL,
    title TEXT NOT NULL,
    canonical_question TEXT NOT NULL,
    short_answer TEXT NOT NULL,
    answer TEXT NOT NULL,
    answer_scope TEXT NOT NULL,
    question_scope TEXT NOT NULL,
    exclusion_scope TEXT NOT NULL,
    source_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
    warnings JSONB NOT NULL DEFAULT '[]'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (run_id, candidate_key)
);

CREATE TABLE IF NOT EXISTS knowledge_surface_local_relations (
    id UUID PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES knowledge_surface_compiler_runs(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,
    source_unit_id UUID NOT NULL REFERENCES knowledge_surface_source_units(id) ON DELETE CASCADE,
    source_surface_key TEXT NOT NULL,
    target_surface_key TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
    reason TEXT NOT NULL,
    source_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS knowledge_surface_rejected_questions (
    id UUID PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES knowledge_surface_compiler_runs(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,
    surface_key TEXT NOT NULL,
    question TEXT NOT NULL,
    belongs_to_surface_key TEXT NOT NULL,
    reason TEXT NOT NULL,
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS knowledge_surface_reconciliation_runs (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,
    run_id UUID NOT NULL REFERENCES knowledge_surface_compiler_runs(id) ON DELETE CASCADE,
    input_candidate_count INTEGER NOT NULL DEFAULT 0,
    input_relation_count INTEGER NOT NULL DEFAULT 0,
    created_parent_count INTEGER NOT NULL DEFAULT 0,
    reparented_surface_count INTEGER NOT NULL DEFAULT 0,
    moved_question_count INTEGER NOT NULL DEFAULT 0,
    merged_candidate_count INTEGER NOT NULL DEFAULT 0,
    warning_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS knowledge_surface_global_relations (
    id UUID PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES knowledge_surface_compiler_runs(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,
    parent_surface_key TEXT NOT NULL,
    child_surface_key TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    reason TEXT NOT NULL,
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
    source_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_surface_candidates_run_id
    ON knowledge_surface_candidates(run_id);
CREATE INDEX IF NOT EXISTS idx_surface_candidates_document_id
    ON knowledge_surface_candidates(document_id);
CREATE INDEX IF NOT EXISTS idx_surface_candidates_source_unit_id
    ON knowledge_surface_candidates(source_unit_id);
CREATE INDEX IF NOT EXISTS idx_surface_answer_drafts_run_id
    ON knowledge_surface_answer_drafts(run_id);
CREATE INDEX IF NOT EXISTS idx_surface_answer_drafts_document_id
    ON knowledge_surface_answer_drafts(document_id);
CREATE INDEX IF NOT EXISTS idx_surface_local_relations_run_id
    ON knowledge_surface_local_relations(run_id);
CREATE INDEX IF NOT EXISTS idx_surface_local_relations_source_unit_id
    ON knowledge_surface_local_relations(source_unit_id);
CREATE INDEX IF NOT EXISTS idx_surface_rejected_questions_run_id
    ON knowledge_surface_rejected_questions(run_id);
CREATE INDEX IF NOT EXISTS idx_surface_rejected_questions_surface_key
    ON knowledge_surface_rejected_questions(surface_key);
CREATE INDEX IF NOT EXISTS idx_surface_reconciliation_runs_run_id
    ON knowledge_surface_reconciliation_runs(run_id);
CREATE INDEX IF NOT EXISTS idx_surface_reconciliation_runs_document_id
    ON knowledge_surface_reconciliation_runs(document_id);
CREATE INDEX IF NOT EXISTS idx_surface_global_relations_run_id
    ON knowledge_surface_global_relations(run_id);
CREATE INDEX IF NOT EXISTS idx_surface_global_relations_parent_key
    ON knowledge_surface_global_relations(parent_surface_key);
CREATE INDEX IF NOT EXISTS idx_surface_global_relations_child_key
    ON knowledge_surface_global_relations(child_surface_key);

COMMIT;
