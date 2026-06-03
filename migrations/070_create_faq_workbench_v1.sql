-- FAQ Workbench v2 persistence foundation.
--
-- Empty-DB destructive cutover.
-- The Workbench source of truth is a claim/fact-registry graph, not FAQ
-- surface findings, question registries, answer candidates, or proposal rows.

CREATE TABLE IF NOT EXISTS knowledge_workbench_documents (
    document_id TEXT PRIMARY KEY,
    storage_id UUID NOT NULL DEFAULT gen_random_uuid() UNIQUE,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    file_name TEXT NOT NULL,
    source_type TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    upload_id TEXT NOT NULL,
    file_size_bytes BIGINT NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    current_processing_run_id TEXT,
    uploaded_by_user_id TEXT,
    uploaded_by_actor_type TEXT NOT NULL DEFAULT 'unknown',
    uploaded_by_actor_id TEXT,
    trusted_upload BOOLEAN NOT NULL DEFAULT FALSE,
    retention_state TEXT NOT NULL DEFAULT 'active_processing',
    last_error_kind TEXT,
    last_error_message TEXT,
    last_error_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at TIMESTAMPTZ,
    CHECK (file_size_bytes >= 0),
    CHECK (uploaded_by_actor_type <> ''),
    CHECK (
        last_error_at IS NULL
        OR last_error_kind IS NOT NULL
        OR last_error_message IS NOT NULL
    )
);

CREATE INDEX IF NOT EXISTS idx_kwb_documents_project_created
    ON knowledge_workbench_documents(project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_kwb_documents_project_status
    ON knowledge_workbench_documents(project_id, status);
CREATE INDEX IF NOT EXISTS idx_kwb_documents_current_run
    ON knowledge_workbench_documents(current_processing_run_id)
    WHERE current_processing_run_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_kwb_documents_retention_state
    ON knowledge_workbench_documents(project_id, document_id, retention_state);

CREATE TABLE IF NOT EXISTS knowledge_workbench_document_sections (
    section_id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES knowledge_workbench_documents(document_id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    section_index INTEGER NOT NULL,
    section_key TEXT NOT NULL,
    heading_path JSONB NOT NULL DEFAULT '[]'::jsonb,
    title TEXT NOT NULL,
    raw_text TEXT NOT NULL,
    normalized_text TEXT NOT NULL,
    source_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_chunk_indexes JSONB NOT NULL DEFAULT '[]'::jsonb,
    parent_section_id TEXT,
    status TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (section_index >= 0)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_kwb_sections_document_key
    ON knowledge_workbench_document_sections(document_id, section_key);
CREATE INDEX IF NOT EXISTS idx_kwb_sections_project_document
    ON knowledge_workbench_document_sections(project_id, document_id, section_index);
CREATE INDEX IF NOT EXISTS idx_kwb_sections_status
    ON knowledge_workbench_document_sections(project_id, document_id, status);

CREATE TABLE IF NOT EXISTS knowledge_workbench_processing_runs (
    processing_run_id TEXT PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    document_id TEXT NOT NULL REFERENCES knowledge_workbench_documents(document_id) ON DELETE CASCADE,
    processing_method TEXT NOT NULL,
    trigger TEXT NOT NULL,
    status TEXT NOT NULL,
    resume_policy TEXT NOT NULL,
    started_at TIMESTAMPTZ,
    stopped_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    deleted_at TIMESTAMPTZ,
    active_elapsed_seconds INTEGER NOT NULL DEFAULT 0,
    wall_elapsed_seconds INTEGER NOT NULL DEFAULT 0,
    total_prompt_tokens INTEGER NOT NULL DEFAULT 0,
    total_completion_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    total_llm_calls INTEGER NOT NULL DEFAULT 0,
    last_error_kind TEXT,
    last_error_report_id TEXT,
    last_user_message TEXT,
    last_internal_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (active_elapsed_seconds >= 0),
    CHECK (wall_elapsed_seconds >= 0),
    CHECK (total_prompt_tokens >= 0),
    CHECK (total_completion_tokens >= 0),
    CHECK (total_tokens >= 0),
    CHECK (total_llm_calls >= 0)
);

CREATE INDEX IF NOT EXISTS idx_kwb_runs_project_document_started
    ON knowledge_workbench_processing_runs(project_id, document_id, started_at DESC NULLS LAST, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_kwb_runs_status
    ON knowledge_workbench_processing_runs(project_id, status);

CREATE TABLE IF NOT EXISTS knowledge_workbench_fact_registries (
    fact_registry_id TEXT PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    document_id TEXT NOT NULL REFERENCES knowledge_workbench_documents(document_id) ON DELETE CASCADE,
    processing_run_id TEXT REFERENCES knowledge_workbench_processing_runs(processing_run_id) ON DELETE SET NULL,
    status TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    retention_state TEXT NOT NULL DEFAULT 'active_processing',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ,
    CHECK (version > 0)
);

CREATE INDEX IF NOT EXISTS idx_kwb_fact_registries_run
    ON knowledge_workbench_fact_registries(project_id, document_id, processing_run_id, version DESC);
CREATE INDEX IF NOT EXISTS idx_kwb_fact_registries_retention_state
    ON knowledge_workbench_fact_registries(project_id, document_id, retention_state);

CREATE TABLE IF NOT EXISTS knowledge_workbench_processing_node_runs (
    node_run_id TEXT PRIMARY KEY,
    processing_run_id TEXT NOT NULL REFERENCES knowledge_workbench_processing_runs(processing_run_id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    document_id TEXT NOT NULL REFERENCES knowledge_workbench_documents(document_id) ON DELETE CASCADE,
    section_id TEXT,
    node_name TEXT NOT NULL,
    node_kind TEXT NOT NULL,
    status TEXT NOT NULL,
    input_snapshot_id TEXT,
    output_snapshot_id TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    duration_ms INTEGER,
    model_name TEXT,
    model_provider TEXT,
    groq_key_slot TEXT,
    prompt_tokens INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    error_kind TEXT,
    error_message_user TEXT,
    error_message_internal TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (duration_ms IS NULL OR duration_ms >= 0),
    CHECK (prompt_tokens >= 0),
    CHECK (completion_tokens >= 0),
    CHECK (total_tokens >= 0)
);

CREATE INDEX IF NOT EXISTS idx_kwb_node_runs_run
    ON knowledge_workbench_processing_node_runs(project_id, document_id, processing_run_id, started_at ASC NULLS LAST, created_at ASC);
CREATE INDEX IF NOT EXISTS idx_kwb_node_runs_section
    ON knowledge_workbench_processing_node_runs(section_id)
    WHERE section_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS knowledge_workbench_processing_node_artifacts (
    artifact_id TEXT PRIMARY KEY,
    node_run_id TEXT NOT NULL REFERENCES knowledge_workbench_processing_node_runs(node_run_id) ON DELETE CASCADE,
    processing_run_id TEXT NOT NULL REFERENCES knowledge_workbench_processing_runs(processing_run_id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    document_id TEXT NOT NULL REFERENCES knowledge_workbench_documents(document_id) ON DELETE CASCADE,
    section_id TEXT,
    artifact_type TEXT NOT NULL,
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    schema_version INTEGER NOT NULL DEFAULT 1,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (schema_version > 0)
);

CREATE INDEX IF NOT EXISTS idx_kwb_node_artifacts_node
    ON knowledge_workbench_processing_node_artifacts(node_run_id);
CREATE INDEX IF NOT EXISTS idx_kwb_node_artifacts_type
    ON knowledge_workbench_processing_node_artifacts(project_id, document_id, processing_run_id, artifact_type);

CREATE TABLE IF NOT EXISTS knowledge_workbench_registry_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    fact_registry_id TEXT NOT NULL REFERENCES knowledge_workbench_fact_registries(fact_registry_id) ON DELETE CASCADE,
    processing_run_id TEXT REFERENCES knowledge_workbench_processing_runs(processing_run_id) ON DELETE SET NULL,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    document_id TEXT NOT NULL REFERENCES knowledge_workbench_documents(document_id) ON DELETE CASCADE,
    after_section_id TEXT,
    after_node_run_id TEXT,
    sequence_number INTEGER NOT NULL,
    fact_registry_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    canonical_fact_count INTEGER NOT NULL DEFAULT 0,
    fact_relation_count INTEGER NOT NULL DEFAULT 0,
    claim_observation_count INTEGER NOT NULL DEFAULT 0,
    update_count INTEGER NOT NULL DEFAULT 0,
    retention_state TEXT NOT NULL DEFAULT 'active_processing',
    is_final_published BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (sequence_number > 0),
    CHECK (canonical_fact_count >= 0),
    CHECK (fact_relation_count >= 0),
    CHECK (claim_observation_count >= 0),
    CHECK (update_count >= 0)
);

CREATE INDEX IF NOT EXISTS idx_kwb_snapshots_latest
    ON knowledge_workbench_registry_snapshots(project_id, document_id, processing_run_id, sequence_number DESC);
CREATE INDEX IF NOT EXISTS idx_kwb_snapshots_final_published
    ON knowledge_workbench_registry_snapshots(project_id, document_id, is_final_published)
    WHERE is_final_published = TRUE;

CREATE TABLE IF NOT EXISTS knowledge_workbench_canonical_facts (
    fact_id TEXT PRIMARY KEY,
    fact_registry_id TEXT NOT NULL REFERENCES knowledge_workbench_fact_registries(fact_registry_id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    document_id TEXT NOT NULL REFERENCES knowledge_workbench_documents(document_id) ON DELETE CASCADE,
    processing_run_id TEXT REFERENCES knowledge_workbench_processing_runs(processing_run_id) ON DELETE SET NULL,
    claim TEXT NOT NULL,
    claim_kind TEXT NOT NULL,
    granularity TEXT NOT NULL,
    possible_questions JSONB NOT NULL DEFAULT '[]'::jsonb,
    scope TEXT NOT NULL DEFAULT '',
    exclusion_scope TEXT NOT NULL DEFAULT '',
    derived_fact_notes JSONB NOT NULL DEFAULT '[]'::jsonb,
    status TEXT NOT NULL,
    retention_state TEXT NOT NULL DEFAULT 'active_processing',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_kwb_canonical_facts_registry
    ON knowledge_workbench_canonical_facts(fact_registry_id, status);
CREATE INDEX IF NOT EXISTS idx_kwb_canonical_facts_document
    ON knowledge_workbench_canonical_facts(project_id, document_id, status);

CREATE TABLE IF NOT EXISTS knowledge_workbench_fact_triples (
    triple_id TEXT PRIMARY KEY,
    fact_id TEXT NOT NULL REFERENCES knowledge_workbench_canonical_facts(fact_id) ON DELETE CASCADE,
    fact_registry_id TEXT NOT NULL REFERENCES knowledge_workbench_fact_registries(fact_registry_id) ON DELETE CASCADE,
    subject TEXT NOT NULL,
    predicate TEXT NOT NULL,
    object TEXT NOT NULL,
    qualifiers JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_kwb_fact_triples_fact
    ON knowledge_workbench_fact_triples(fact_id);
CREATE INDEX IF NOT EXISTS idx_kwb_fact_triples_spo
    ON knowledge_workbench_fact_triples(subject, predicate, object);

CREATE TABLE IF NOT EXISTS knowledge_workbench_fact_mentions (
    mention_id TEXT PRIMARY KEY,
    fact_id TEXT NOT NULL REFERENCES knowledge_workbench_canonical_facts(fact_id) ON DELETE CASCADE,
    fact_registry_id TEXT NOT NULL REFERENCES knowledge_workbench_fact_registries(fact_registry_id) ON DELETE CASCADE,
    source_section_id TEXT REFERENCES knowledge_workbench_document_sections(section_id) ON DELETE SET NULL,
    source_section_ref TEXT NOT NULL DEFAULT '',
    source_local_ref TEXT NOT NULL DEFAULT '',
    evidence_block TEXT NOT NULL DEFAULT '',
    mention_relation TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_kwb_fact_mentions_fact
    ON knowledge_workbench_fact_mentions(fact_id);
CREATE INDEX IF NOT EXISTS idx_kwb_fact_mentions_section
    ON knowledge_workbench_fact_mentions(source_section_id)
    WHERE source_section_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS knowledge_workbench_fact_relations (
    relation_id TEXT PRIMARY KEY,
    fact_registry_id TEXT NOT NULL REFERENCES knowledge_workbench_fact_registries(fact_registry_id) ON DELETE CASCADE,
    source_fact_id TEXT NOT NULL REFERENCES knowledge_workbench_canonical_facts(fact_id) ON DELETE CASCADE,
    target_fact_id TEXT NOT NULL REFERENCES knowledge_workbench_canonical_facts(fact_id) ON DELETE CASCADE,
    relation TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (source_fact_id <> target_fact_id)
);

CREATE INDEX IF NOT EXISTS idx_kwb_fact_relations_source
    ON knowledge_workbench_fact_relations(source_fact_id);
CREATE INDEX IF NOT EXISTS idx_kwb_fact_relations_target
    ON knowledge_workbench_fact_relations(target_fact_id);

CREATE TABLE IF NOT EXISTS knowledge_workbench_fact_registry_applications (
    application_id TEXT PRIMARY KEY,
    processing_run_id TEXT NOT NULL REFERENCES knowledge_workbench_processing_runs(processing_run_id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    document_id TEXT NOT NULL REFERENCES knowledge_workbench_documents(document_id) ON DELETE CASCADE,
    section_id TEXT,
    fact_registry_node_run_id TEXT REFERENCES knowledge_workbench_processing_node_runs(node_run_id) ON DELETE SET NULL,
    applied_by TEXT NOT NULL,
    before_snapshot_id TEXT,
    after_snapshot_id TEXT,
    claim_input_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
    registry_update_summary JSONB NOT NULL DEFAULT '{}'::jsonb,
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_kwb_fact_registry_applications_run
    ON knowledge_workbench_fact_registry_applications(project_id, document_id, processing_run_id);

CREATE TABLE IF NOT EXISTS knowledge_workbench_runtime_publications (
    publication_id TEXT PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    source TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_kwb_runtime_publications_project
    ON knowledge_workbench_runtime_publications(project_id, created_at DESC);

CREATE TABLE IF NOT EXISTS knowledge_workbench_runtime_retrieval_entries (
    runtime_entry_id TEXT PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    fact_id TEXT NOT NULL REFERENCES knowledge_workbench_canonical_facts(fact_id) ON DELETE CASCADE,
    claim TEXT NOT NULL,
    possible_questions JSONB NOT NULL DEFAULT '[]'::jsonb,
    answer_text TEXT NOT NULL,
    embedding_text TEXT NOT NULL,
    source_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
    visibility TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_kwb_runtime_entries_project_status
    ON knowledge_workbench_runtime_retrieval_entries(project_id, status, visibility);
CREATE INDEX IF NOT EXISTS idx_kwb_runtime_entries_fact
    ON knowledge_workbench_runtime_retrieval_entries(fact_id);
