-- Project member invitations by email/link.
-- Raw invite tokens must never be persisted; only token_hash is stored.

CREATE TABLE IF NOT EXISTS project_invitations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    email text NOT NULL,
    first_name text,
    last_name text,
    role text NOT NULL,
    token_hash text NOT NULL UNIQUE,
    invited_by_user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    accepted_by_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
    expires_at timestamptz NOT NULL,
    accepted_at timestamptz,
    revoked_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_project_invitations_role CHECK (role IN ('admin', 'manager'))
);

CREATE INDEX IF NOT EXISTS idx_project_invitations_project
    ON project_invitations(project_id);

CREATE INDEX IF NOT EXISTS idx_project_invitations_email
    ON project_invitations(email);

CREATE INDEX IF NOT EXISTS idx_project_invitations_pending
    ON project_invitations(project_id, email)
    WHERE accepted_at IS NULL AND revoked_at IS NULL;
