-- Identity layer: связь пользователей с провайдерами
CREATE TABLE auth_identities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,  -- 'telegram', 'email', 'google'
    provider_id TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(provider, provider_id)
);
CREATE INDEX idx_auth_identities_user ON auth_identities(user_id);

-- Каналы (Telegram, веб-виджет и др.)
CREATE TABLE channels (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    type TEXT NOT NULL,  -- 'telegram', 'web_widget'
    config JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_channels_project ON channels(project_id);

-- Фичи проекта (демо-режим, политики эскалации, настройки RAG)
CREATE TABLE features (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    type TEXT NOT NULL,  -- 'demo_mode', 'escalation_policy', 'rag_settings'
    config JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_features_project ON features(project_id);

-- Аналитика по тредам
CREATE TABLE thread_metrics (
    thread_id UUID PRIMARY KEY REFERENCES threads(id) ON DELETE CASCADE,
    total_messages INT DEFAULT 0,
    ai_messages INT DEFAULT 0,
    manager_messages INT DEFAULT 0,
    escalated BOOLEAN DEFAULT false,
    resolution_time INTERVAL,
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Ежедневная агрегация по проектам
CREATE TABLE project_metrics_daily (
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    date DATE NOT NULL,
    total_threads INT DEFAULT 0,
    escalations INT DEFAULT 0,
    avg_messages_to_resolution FLOAT,
    tokens_used INT DEFAULT 0,
    PRIMARY KEY (project_id, date)
);
