-- Canonical upload document metadata.
-- Retired tail: old knowledge_base.document_id linkage moved to
-- migrations/_retired_legacy/035_create_knowledge_documents.sql.

CREATE TABLE IF NOT EXISTS knowledge_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    file_name TEXT NOT NULL,
    file_size BIGINT,
    status TEXT NOT NULL DEFAULT 'pending',
    error TEXT,
    uploaded_by TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);
