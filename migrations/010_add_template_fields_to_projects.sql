-- Migration: 010_add_template_fields_to_projects
-- Purpose: Add template tracking and pro mode flag to projects
-- Enables template-based project creation and canvas access control

ALTER TABLE projects 
ADD COLUMN IF NOT EXISTS template_slug TEXT DEFAULT NULL;

ALTER TABLE projects 
ADD COLUMN IF NOT EXISTS is_pro_mode BOOLEAN DEFAULT false;

-- Index for pro mode filtering
CREATE INDEX IF NOT EXISTS idx_projects_pro_mode ON projects(is_pro_mode) WHERE is_pro_mode = true;

-- Index for template slug
CREATE INDEX IF NOT EXISTS idx_projects_template ON projects(template_slug);

-- Foreign key to templates (optional, can be NULL)
-- Note: No ON DELETE CASCADE - template deletion should not affect projects

-- Comment for documentation
COMMENT ON COLUMN projects.template_slug IS 'Slug of the workflow template applied to this project';
COMMENT ON COLUMN projects.is_pro_mode IS 'Flag indicating if project has access to custom workflow canvas';
