BEGIN;

CREATE TABLE IF NOT EXISTS knowledge_surface_compiler_runs (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,
    mode TEXT NOT NULL,
    status TEXT NOT NULL,
    compiler_kind TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    started_at TIMESTAMPTZ NULL,
    completed_at TIMESTAMPTZ NULL,
    error_type TEXT NULL,
    error_message TEXT NULL,
    metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS knowledge_surface_compiler_stages (
    id UUID PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES knowledge_surface_compiler_runs(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,
    stage_kind TEXT NOT NULL,
    status TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    input_summary TEXT NOT NULL DEFAULT '',
    output_summary TEXT NOT NULL DEFAULT '',
    tokens_input INTEGER NOT NULL DEFAULT 0,
    tokens_output INTEGER NOT NULL DEFAULT 0,
    tokens_total INTEGER NOT NULL DEFAULT 0,
    error_type TEXT NULL,
    error_message TEXT NULL,
    metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
    started_at TIMESTAMPTZ NULL,
    completed_at TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS knowledge_surface_source_units (
    id UUID PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES knowledge_surface_compiler_runs(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,
    source_unit_key TEXT NOT NULL,
    source_chunk_indexes INTEGER[] NOT NULL DEFAULT '{}',
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    children JSONB NOT NULL DEFAULT '[]'::jsonb,
    raw_text TEXT NOT NULL,
    section_path TEXT[] NOT NULL DEFAULT '{}',
    source_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
    preprocessing_mode TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS knowledge_surfaces (
    id UUID PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES knowledge_surface_compiler_runs(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,
    local_surface_key TEXT NOT NULL,
    title TEXT NOT NULL,
    canonical_question TEXT NOT NULL,
    surface_kind TEXT NOT NULL,
    answer_scope TEXT NOT NULL,
    question_scope TEXT NOT NULL,
    exclusion_scope TEXT NOT NULL,
    answer TEXT NOT NULL,
    short_answer TEXT NOT NULL,
    status TEXT NOT NULL,
    publication_status TEXT NOT NULL,
    source_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_excerpt TEXT NOT NULL DEFAULT '',
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
    warnings JSONB NOT NULL DEFAULT '[]'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    source_chunk_indexes INTEGER[] NOT NULL DEFAULT '{}',
    linked_candidate_id UUID NULL,
    linked_canonical_entry_id UUID NULL,
    linked_runtime_entry_id UUID NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS knowledge_surface_relations (
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

CREATE TABLE IF NOT EXISTS knowledge_surface_question_ownership (
    id UUID PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES knowledge_surface_compiler_runs(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,
    question TEXT NOT NULL,
    owner_surface_key TEXT NOT NULL,
    question_kind TEXT NOT NULL,
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
    reason TEXT NOT NULL,
    rejected_from_surface_keys JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS knowledge_surface_question_reassignments (
    id UUID PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES knowledge_surface_compiler_runs(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,
    question TEXT NOT NULL,
    from_surface_key TEXT NOT NULL,
    to_surface_key TEXT NOT NULL,
    reason TEXT NOT NULL,
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS knowledge_surface_merge_decisions (
    id UUID PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES knowledge_surface_compiler_runs(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,
    survivor_surface_key TEXT NOT NULL,
    merged_surface_keys JSONB NOT NULL DEFAULT '[]'::jsonb,
    keep_separate_surface_keys JSONB NOT NULL DEFAULT '[]'::jsonb,
    decision_type TEXT NOT NULL,
    reason TEXT NOT NULL,
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_surface_runs_project_id ON knowledge_surface_compiler_runs(project_id);
CREATE INDEX IF NOT EXISTS idx_surface_runs_document_id ON knowledge_surface_compiler_runs(document_id);
CREATE INDEX IF NOT EXISTS idx_surface_stages_run_id ON knowledge_surface_compiler_stages(run_id);
CREATE INDEX IF NOT EXISTS idx_surface_stages_document_id ON knowledge_surface_compiler_stages(document_id);
CREATE INDEX IF NOT EXISTS idx_surface_source_units_run_id ON knowledge_surface_source_units(run_id);
CREATE INDEX IF NOT EXISTS idx_surface_source_units_document_id ON knowledge_surface_source_units(document_id);
CREATE INDEX IF NOT EXISTS idx_surfaces_run_id ON knowledge_surfaces(run_id);
CREATE INDEX IF NOT EXISTS idx_surfaces_document_id ON knowledge_surfaces(document_id);
CREATE INDEX IF NOT EXISTS idx_surfaces_local_surface_key ON knowledge_surfaces(local_surface_key);
CREATE INDEX IF NOT EXISTS idx_surfaces_surface_kind ON knowledge_surfaces(surface_kind);
CREATE INDEX IF NOT EXISTS idx_surfaces_status ON knowledge_surfaces(status);
CREATE INDEX IF NOT EXISTS idx_surfaces_publication_status ON knowledge_surfaces(publication_status);
CREATE INDEX IF NOT EXISTS idx_surface_relations_run_id ON knowledge_surface_relations(run_id);
CREATE INDEX IF NOT EXISTS idx_surface_relations_parent_surface_key ON knowledge_surface_relations(parent_surface_key);
CREATE INDEX IF NOT EXISTS idx_surface_relations_child_surface_key ON knowledge_surface_relations(child_surface_key);
CREATE INDEX IF NOT EXISTS idx_surface_ownership_run_id ON knowledge_surface_question_ownership(run_id);
CREATE INDEX IF NOT EXISTS idx_surface_ownership_owner_surface_key ON knowledge_surface_question_ownership(owner_surface_key);
CREATE INDEX IF NOT EXISTS idx_surface_reassignments_run_id ON knowledge_surface_question_reassignments(run_id);
CREATE INDEX IF NOT EXISTS idx_surface_merge_decisions_run_id ON knowledge_surface_merge_decisions(run_id);

COMMIT;
