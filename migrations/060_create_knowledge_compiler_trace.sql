-- Migration 060: KCD v1 Stage E compiler trace persistence.
--
-- Target architecture:
-- - CompilerRun is persisted separately from knowledge_entries.
-- - CompilationMetrics is persisted as first-class counters.
-- - AnswerCandidate rows preserve extracted/merged/rejected compiler candidates.
-- - CandidateCluster rows preserve clustering/merge traceability.
-- - Runtime retrieval remains knowledge_retrieval_surface from Stage C+D.
-- - RAG eval chunk naming is intentionally deferred to Stage G.

BEGIN;

CREATE TABLE IF NOT EXISTS knowledge_compiler_runs (
    id TEXT PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,
    mode TEXT NOT NULL,
    compiler_version TEXT NOT NULL,
    prompt_version TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'created',
    error TEXT NOT NULL DEFAULT '',
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    created_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ck_knowledge_compiler_runs_id_not_blank CHECK (btrim(id) <> ''),
    CONSTRAINT ck_knowledge_compiler_runs_mode_not_blank CHECK (btrim(mode) <> ''),
    CONSTRAINT ck_knowledge_compiler_runs_compiler_version_not_blank CHECK (btrim(compiler_version) <> ''),
    CONSTRAINT ck_knowledge_compiler_runs_status CHECK (
        status IN ('created', 'running', 'completed', 'failed')
    ),
    CONSTRAINT ck_knowledge_compiler_runs_finished_after_started CHECK (
        started_at IS NULL
        OR finished_at IS NULL
        OR finished_at >= started_at
    )
);

CREATE TABLE IF NOT EXISTS knowledge_compilation_metrics (
    compiler_run_id TEXT PRIMARY KEY REFERENCES knowledge_compiler_runs(id) ON DELETE CASCADE,
    source_chunk_count INTEGER NOT NULL DEFAULT 0,
    answer_candidate_count INTEGER NOT NULL DEFAULT 0,
    grounded_candidate_count INTEGER NOT NULL DEFAULT 0,
    rejected_candidate_count INTEGER NOT NULL DEFAULT 0,
    candidate_cluster_count INTEGER NOT NULL DEFAULT 0,
    canonical_entry_count INTEGER NOT NULL DEFAULT 0,
    enriched_entry_count INTEGER NOT NULL DEFAULT 0,
    embedded_entry_count INTEGER NOT NULL DEFAULT 0,
    published_entry_count INTEGER NOT NULL DEFAULT 0,
    fallback_row_count INTEGER NOT NULL DEFAULT 0,
    dropped_forbidden_count INTEGER NOT NULL DEFAULT 0,
    entries_without_source_refs_count INTEGER NOT NULL DEFAULT 0,
    metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ck_knowledge_compilation_metrics_non_negative CHECK (
        source_chunk_count >= 0
        AND answer_candidate_count >= 0
        AND grounded_candidate_count >= 0
        AND rejected_candidate_count >= 0
        AND candidate_cluster_count >= 0
        AND canonical_entry_count >= 0
        AND enriched_entry_count >= 0
        AND embedded_entry_count >= 0
        AND published_entry_count >= 0
        AND fallback_row_count >= 0
        AND dropped_forbidden_count >= 0
        AND entries_without_source_refs_count >= 0
    )
);

CREATE TABLE IF NOT EXISTS knowledge_answer_candidates (
    id TEXT PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,
    compiler_run_id TEXT NOT NULL REFERENCES knowledge_compiler_runs(id) ON DELETE CASCADE,
    topic_key TEXT NOT NULL,
    title TEXT NOT NULL,
    candidate_answer TEXT NOT NULL,
    source_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
    confidence DOUBLE PRECISION,
    status TEXT NOT NULL DEFAULT 'extracted',
    rejection_reason TEXT NOT NULL DEFAULT '',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ck_knowledge_answer_candidates_id_not_blank CHECK (btrim(id) <> ''),
    CONSTRAINT ck_knowledge_answer_candidates_topic_key_not_blank CHECK (btrim(topic_key) <> ''),
    CONSTRAINT ck_knowledge_answer_candidates_title_not_blank CHECK (btrim(title) <> ''),
    CONSTRAINT ck_knowledge_answer_candidates_answer_not_blank CHECK (btrim(candidate_answer) <> ''),
    CONSTRAINT ck_knowledge_answer_candidates_confidence CHECK (
        confidence IS NULL
        OR (confidence >= 0.0 AND confidence <= 1.0)
    ),
    CONSTRAINT ck_knowledge_answer_candidates_status CHECK (
        status IN (
            'extracted',
            'grounded_checked',
            'clustered',
            'merged',
            'rejected'
        )
    )
);

CREATE TABLE IF NOT EXISTS knowledge_candidate_clusters (
    id TEXT PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,
    compiler_run_id TEXT NOT NULL REFERENCES knowledge_compiler_runs(id) ON DELETE CASCADE,
    cluster_key TEXT NOT NULL,
    topic TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'created',
    merge_strategy TEXT NOT NULL DEFAULT '',
    merge_reason TEXT NOT NULL DEFAULT '',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_knowledge_candidate_clusters_run_key UNIQUE (compiler_run_id, cluster_key),
    CONSTRAINT ck_knowledge_candidate_clusters_id_not_blank CHECK (btrim(id) <> ''),
    CONSTRAINT ck_knowledge_candidate_clusters_key_not_blank CHECK (btrim(cluster_key) <> ''),
    CONSTRAINT ck_knowledge_candidate_clusters_topic_not_blank CHECK (btrim(topic) <> ''),
    CONSTRAINT ck_knowledge_candidate_clusters_status CHECK (
        status IN (
            'created',
            'merge_ready',
            'canonical_entry_created',
            'needs_review'
        )
    )
);

CREATE TABLE IF NOT EXISTS knowledge_candidate_cluster_members (
    cluster_id TEXT NOT NULL REFERENCES knowledge_candidate_clusters(id) ON DELETE CASCADE,
    candidate_id TEXT NOT NULL REFERENCES knowledge_answer_candidates(id) ON DELETE CASCADE,
    candidate_index INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT pk_knowledge_candidate_cluster_members PRIMARY KEY (cluster_id, candidate_id),
    CONSTRAINT uq_knowledge_candidate_cluster_members_position UNIQUE (cluster_id, candidate_index),
    CONSTRAINT ck_knowledge_candidate_cluster_members_index CHECK (candidate_index >= 0)
);

CREATE INDEX IF NOT EXISTS idx_knowledge_compiler_runs_project_document
    ON knowledge_compiler_runs(project_id, document_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_knowledge_compiler_runs_status
    ON knowledge_compiler_runs(status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_knowledge_answer_candidates_run
    ON knowledge_answer_candidates(compiler_run_id, status);

CREATE INDEX IF NOT EXISTS idx_knowledge_answer_candidates_document
    ON knowledge_answer_candidates(project_id, document_id);

CREATE INDEX IF NOT EXISTS idx_knowledge_candidate_clusters_run
    ON knowledge_candidate_clusters(compiler_run_id, status);

CREATE INDEX IF NOT EXISTS idx_knowledge_candidate_cluster_members_candidate
    ON knowledge_candidate_cluster_members(candidate_id);

ANALYZE knowledge_compiler_runs;
ANALYZE knowledge_compilation_metrics;
ANALYZE knowledge_answer_candidates;
ANALYZE knowledge_candidate_clusters;
ANALYZE knowledge_candidate_cluster_members;

COMMIT;
