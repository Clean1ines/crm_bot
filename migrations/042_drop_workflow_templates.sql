-- Migration 042: Remove legacy workflow templates from the product model.
--
-- Templates were an early onboarding shortcut, but project behavior is now
-- configured through project-scoped settings, policies, integrations, limits,
-- prompt versions, knowledge, and optional custom workflows.

DROP INDEX IF EXISTS idx_projects_template;
DROP INDEX IF EXISTS idx_projects_template_slug;
DROP INDEX IF EXISTS idx_templates_active;
DROP INDEX IF EXISTS idx_templates_slug;

ALTER TABLE projects
    DROP COLUMN IF EXISTS template_slug;

DROP TABLE IF EXISTS workflow_templates;
