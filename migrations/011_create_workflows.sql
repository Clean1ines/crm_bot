-- Migration: 011_create_workflows
-- Purpose: Custom workflow storage for Pro mode projects
-- Allows users to create and save custom graph configurations

CREATE TABLE IF NOT EXISTS workflows (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    graph_json JSONB NOT NULL,
    version INTEGER DEFAULT 1,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- Index for project workflows
CREATE INDEX IF NOT EXISTS idx_workflows_project ON workflows(project_id);

-- Index for active workflow lookup
CREATE INDEX IF NOT EXISTS idx_workflows_active ON workflows(project_id, is_active) WHERE is_active = true;

-- Foreign key to projects
ALTER TABLE workflows 
ADD CONSTRAINT fk_workflows_project 
FOREIGN KEY (project_id) 
REFERENCES projects(id) 
ON DELETE CASCADE;

-- Comment for documentation
COMMENT ON TABLE workflows IS 'Custom workflow definitions for Pro mode projects';
COMMENT ON COLUMN workflows.version IS 'Version number for workflow (incremented on each update)';
COMMENT ON COLUMN workflows.graph_json IS 'LangGraph-compatible graph definition from canvas';
