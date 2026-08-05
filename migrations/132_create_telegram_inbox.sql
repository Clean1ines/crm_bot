ALTER TABLE projects
    ADD COLUMN IF NOT EXISTS client_telegram_bot_id BIGINT,
    ADD COLUMN IF NOT EXISTS manager_telegram_bot_id BIGINT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_projects_client_telegram_bot_id_positive'
    ) THEN
        ALTER TABLE public.projects
            ADD CONSTRAINT ck_projects_client_telegram_bot_id_positive
            CHECK (client_telegram_bot_id IS NULL OR client_telegram_bot_id > 0);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_projects_manager_telegram_bot_id_positive'
    ) THEN
        ALTER TABLE public.projects
            ADD CONSTRAINT ck_projects_manager_telegram_bot_id_positive
            CHECK (manager_telegram_bot_id IS NULL OR manager_telegram_bot_id > 0);
    END IF;
END $$;

COMMENT ON COLUMN projects.client_telegram_bot_id IS 'Numeric Telegram account id for the project client bot.';
COMMENT ON COLUMN projects.manager_telegram_bot_id IS 'Numeric Telegram account id for the project manager bot.';

CREATE TABLE IF NOT EXISTS public.platform_telegram_bot_configurations (
    platform_scope TEXT PRIMARY KEY,
    telegram_bot_id BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_platform_telegram_bot_id_positive'
    ) THEN
        ALTER TABLE public.platform_telegram_bot_configurations
            ADD CONSTRAINT ck_platform_telegram_bot_id_positive
            CHECK (telegram_bot_id IS NULL OR telegram_bot_id > 0);
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS public.telegram_inbox_updates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    surface TEXT NOT NULL,
    project_id UUID REFERENCES public.projects(id) ON DELETE CASCADE,
    platform_scope TEXT,
    telegram_bot_id BIGINT NOT NULL,
    telegram_update_id BIGINT NOT NULL,
    original_payload JSONB NOT NULL,
    original_payload_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'received',
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    failed_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    owned_by TEXT,
    owner_token TEXT,
    lease_expires_at TIMESTAMPTZ,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    last_error_kind TEXT,
    last_error_message TEXT,
    next_attempt_at TIMESTAMPTZ,
    duplicate_count INTEGER NOT NULL DEFAULT 0,
    last_duplicate_at TIMESTAMPTZ,
    payload_anomaly_count INTEGER NOT NULL DEFAULT 0,
    last_payload_anomaly_at TIMESTAMPTZ,
    last_payload_anomaly_hash TEXT,
    CONSTRAINT ck_telegram_inbox_surface
        CHECK (surface IN ('client', 'manager', 'platform_admin')),
    CONSTRAINT ck_telegram_inbox_status
        CHECK (status IN (
            'received',
            'processing',
            'completed',
            'retryable_failed',
            'terminal_failed'
        )),
    CONSTRAINT ck_telegram_inbox_scope
        CHECK (
            (
                surface IN ('client', 'manager')
                AND project_id IS NOT NULL
                AND platform_scope IS NULL
            )
            OR (
                surface = 'platform_admin'
                AND project_id IS NULL
                AND platform_scope IS NOT NULL
            )
        ),
    CONSTRAINT ck_telegram_inbox_positive_bot_id
        CHECK (telegram_bot_id > 0),
    CONSTRAINT ck_telegram_inbox_non_negative_update_id
        CHECK (telegram_update_id >= 0),
    CONSTRAINT ck_telegram_inbox_attempt_count
        CHECK (attempt_count >= 0),
    CONSTRAINT ck_telegram_inbox_duplicate_count
        CHECK (duplicate_count >= 0),
    CONSTRAINT ck_telegram_inbox_payload_anomaly_count
        CHECK (payload_anomaly_count >= 0),
    CONSTRAINT ck_telegram_inbox_processing_owner
        CHECK (
            (
                status = 'processing'
                AND owned_by IS NOT NULL
                AND owner_token IS NOT NULL
                AND lease_expires_at IS NOT NULL
            )
            OR (
                status <> 'processing'
                AND owned_by IS NULL
                AND owner_token IS NULL
                AND lease_expires_at IS NULL
            )
        )
);

ALTER TABLE public.telegram_inbox_updates
    DROP CONSTRAINT IF EXISTS ck_telegram_inbox_processing_owner;

ALTER TABLE public.telegram_inbox_updates
    ADD CONSTRAINT ck_telegram_inbox_processing_owner
    CHECK (
        (
            status = 'processing'
            AND owned_by IS NOT NULL
            AND owner_token IS NOT NULL
            AND lease_expires_at IS NOT NULL
        )
        OR (
            status <> 'processing'
            AND owned_by IS NULL
            AND owner_token IS NULL
            AND lease_expires_at IS NULL
        )
    );

CREATE UNIQUE INDEX IF NOT EXISTS uq_telegram_inbox_project_update_identity
    ON public.telegram_inbox_updates (
        surface,
        project_id,
        telegram_bot_id,
        telegram_update_id
    )
    WHERE project_id IS NOT NULL AND platform_scope IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_telegram_inbox_platform_update_identity
    ON public.telegram_inbox_updates (
        surface,
        platform_scope,
        telegram_bot_id,
        telegram_update_id
    )
    WHERE project_id IS NULL AND platform_scope IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_telegram_inbox_due
    ON public.telegram_inbox_updates (
        status,
        next_attempt_at,
        received_at,
        id
    );

CREATE INDEX IF NOT EXISTS idx_telegram_inbox_expired_processing
    ON public.telegram_inbox_updates (lease_expires_at)
    WHERE status = 'processing';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'ck_telegram_inbox_scope'
    ) THEN
        ALTER TABLE public.telegram_inbox_updates
            ADD CONSTRAINT ck_telegram_inbox_scope
            CHECK (
                (
                    surface IN ('client', 'manager')
                    AND project_id IS NOT NULL
                    AND platform_scope IS NULL
                )
                OR (
                    surface = 'platform_admin'
                    AND project_id IS NULL
                    AND platform_scope IS NOT NULL
                )
            );
    END IF;
END $$;

COMMENT ON TABLE public.telegram_inbox_updates IS 'Durable PostgreSQL intake and lifecycle for Telegram updates.';
