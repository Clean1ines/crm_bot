-- Migration 044: Move CRM card fields to project-scoped clients/contacts.
--
-- users are platform identities. CRM/contact fields belong to clients because
-- a person can be a different contact in different project contexts.

ALTER TABLE clients
    ADD COLUMN IF NOT EXISTS email text,
    ADD COLUMN IF NOT EXISTS company text,
    ADD COLUMN IF NOT EXISTS phone text,
    ADD COLUMN IF NOT EXISTS metadata jsonb NOT NULL DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS idx_clients_project_email ON clients(project_id, email);
