-- Migration 061: durable knowledge compiler batch trace.
--
-- Adds batch-level persistence for Stage K answer compilation so long-running
-- document processing can report honest progress and later support retry/resume
-- without relying only on queue payload state.

BEGIN;

CREATE TABLE IF NOT EXISTS knowledge_compiler_batches (
    id TEXT PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,
    compiler_run_id TEXT NOT NULL REFERENCES knowledge_compiler_runs(id) ON DELETE CASCADE,
    batch_index INTEGER NOT NULL,
    batch_count INTEGER NOT NULL,
    source_chunk_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_chunk_indexes JSONB NOT NULL DEFAULT '[]'::jsonb,
    status TEXT NOT NULL DEFAULT 'pending',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    model TEXT NOT NULL DEFAULT '',
    prompt_version TEXT NOT NULL DEFAULT '',
    tokens_input INTEGER NOT NULL DEFAULT 0,
    tokens_output INTEGER NOT NULL DEFAULT 0,
    tokens_total INTEGER NOT NULL DEFAULT 0,
    error_type TEXT NOT NULL DEFAULT '',
    error_message TEXT NOT NULL DEFAULT '',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ck_knowledge_compiler_batches_id_not_blank CHECK (btrim(id) <> ''),
    CONSTRAINT uq_knowledge_compiler_batches_run_index UNIQUE (compiler_run_id, batch_index),
    CONSTRAINT ck_knowledge_compiler_batches_index CHECK (batch_index >= 1),
    CONSTRAINT ck_knowledge_compiler_batches_count CHECK (batch_count >= 1),
    CONSTRAINT ck_knowledge_compiler_batches_index_within_count CHECK (batch_index <= batch_count),
    CONSTRAINT ck_knowledge_compiler_batches_status CHECK (
        status IN ('pending', 'processing', 'completed', 'failed', 'skipped', 'cancelled')
    ),
    CONSTRAINT ck_knowledge_compiler_batches_non_negative CHECK (
        attempt_count >= 0
        AND tokens_input >= 0
        AND tokens_output >= 0
        AND tokens_total >= 0
    ),
    CONSTRAINT ck_knowledge_compiler_batches_finished_after_started CHECK (
        started_at IS NULL
        OR finished_at IS NULL
        OR finished_at >= started_at
    )
);

CREATE INDEX IF NOT EXISTS idx_knowledge_compiler_batches_run_status
    ON knowledge_compiler_batches(compiler_run_id, status, batch_index);

CREATE INDEX IF NOT EXISTS idx_knowledge_compiler_batches_document
    ON knowledge_compiler_batches(project_id, document_id, batch_index);

ANALYZE knowledge_compiler_batches;

COMMIT;
