-- Table for managing documents uploaded to knowledge base
CREATE TABLE knowledge_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    file_name TEXT NOT NULL,
    file_size BIGINT,
    status TEXT NOT NULL DEFAULT 'pending', -- pending, processing, completed, failed
    error TEXT,
    uploaded_by TEXT, -- can be user_id or telegram_id
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Add document_id to knowledge_base to link chunks to source document
ALTER TABLE knowledge_base ADD COLUMN document_id UUID REFERENCES knowledge_documents(id) ON DELETE SET NULL;
CREATE INDEX idx_knowledge_base_document ON knowledge_base(document_id);
