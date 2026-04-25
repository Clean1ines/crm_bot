-- Migration: 037_add_auth_membership_and_personalization
-- Purpose: Introduce canonical project membership, auth security tables,
-- and explicit project personalization/configuration tables.

BEGIN;

-- ---------------------------------------------------------------------
-- Project membership: canonical source of truth for project roles
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS project_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_project_members_project_user UNIQUE (project_id, user_id),
    CONSTRAINT ck_project_members_role CHECK (role IN ('owner', 'admin', 'manager', 'viewer'))
);

CREATE INDEX IF NOT EXISTS idx_project_members_project ON project_members(project_id);
CREATE INDEX IF NOT EXISTS idx_project_members_user ON project_members(user_id);
CREATE INDEX IF NOT EXISTS idx_project_members_role ON project_members(role);

-- Backfill managers that already have Telegram identities into project_members.
INSERT INTO project_members (project_id, user_id, role)
SELECT pm.project_id, ai.user_id, 'manager'
FROM project_managers pm
JOIN auth_identities ai
  ON ai.provider = 'telegram'
 AND ai.provider_id = pm.manager_chat_id
ON CONFLICT (project_id, user_id) DO NOTHING;

-- Some legacy users may still have users.telegram_id but no auth_identities row yet.
INSERT INTO project_members (project_id, user_id, role)
SELECT pm.project_id, u.id, 'manager'
FROM project_managers pm
JOIN users u
  ON CAST(u.telegram_id AS TEXT) = pm.manager_chat_id
WHERE u.telegram_id IS NOT NULL
ON CONFLICT (project_id, user_id) DO NOTHING;

-- ---------------------------------------------------------------------
-- Auth security tables
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS user_credentials (
    user_id UUID PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    password_hash TEXT NOT NULL,
    password_updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS email_verification_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    token TEXT NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_email_verification_tokens_user
    ON email_verification_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_email_verification_tokens_email
    ON email_verification_tokens(email);

CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token TEXT NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_user
    ON password_reset_tokens(user_id);

CREATE TABLE IF NOT EXISTS oauth_link_states (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    state TEXT NOT NULL UNIQUE,
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_oauth_link_states_user
    ON oauth_link_states(user_id);
CREATE INDEX IF NOT EXISTS idx_oauth_link_states_provider
    ON oauth_link_states(provider);

-- ---------------------------------------------------------------------
-- Project personalization/configuration tables
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS project_settings (
    project_id UUID PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
    brand_name TEXT,
    industry TEXT,
    tone_of_voice TEXT,
    default_language TEXT,
    default_timezone TEXT,
    system_prompt_override TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS project_policies (
    project_id UUID PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
    escalation_policy_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    routing_policy_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    crm_policy_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    response_policy_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    privacy_policy_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS project_integrations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'disabled',
    credentials_encrypted TEXT,
    config_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_project_integrations_project_provider UNIQUE (project_id, provider)
);

CREATE INDEX IF NOT EXISTS idx_project_integrations_project
    ON project_integrations(project_id);
CREATE INDEX IF NOT EXISTS idx_project_integrations_provider
    ON project_integrations(provider);

CREATE TABLE IF NOT EXISTS project_limit_profiles (
    project_id UUID PRIMARY KEY REFERENCES projects(id) ON DELETE CASCADE,
    monthly_token_limit INTEGER,
    requests_per_minute INTEGER,
    max_concurrent_threads INTEGER,
    priority INTEGER NOT NULL DEFAULT 0,
    fallback_model TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS project_channels (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    provider TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'disabled',
    config_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_project_channels_project_kind_provider UNIQUE (project_id, kind, provider)
);

CREATE INDEX IF NOT EXISTS idx_project_channels_project
    ON project_channels(project_id);
CREATE INDEX IF NOT EXISTS idx_project_channels_kind
    ON project_channels(kind);
CREATE INDEX IF NOT EXISTS idx_project_channels_provider
    ON project_channels(provider);

CREATE TABLE IF NOT EXISTS project_prompt_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    prompt_json JSONB NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    is_active BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT uq_project_prompt_versions_project_name_version UNIQUE (project_id, name, version)
);

CREATE INDEX IF NOT EXISTS idx_project_prompt_versions_project
    ON project_prompt_versions(project_id);
CREATE INDEX IF NOT EXISTS idx_project_prompt_versions_active
    ON project_prompt_versions(project_id, is_active) WHERE is_active = true;

COMMIT;
