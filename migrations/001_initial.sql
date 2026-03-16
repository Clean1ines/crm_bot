CREATE EXTENSION IF NOT EXISTS vector;

-- 1. Таблица проектов (Бизнесы/Клиенты CRM)
CREATE TABLE IF NOT EXISTS public.projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    owner_id UUID, -- Твой ID как админа системы
    bot_token TEXT, -- Токен конкретного бота для этого бизнеса
    system_prompt TEXT DEFAULT 'Ты — полезный AI-ассистент.', -- Инструкция поведения
    webhook_url TEXT, -- Куда слать уведомления о лидах
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 2. Таблица клиентов (Юзеры в телеграме)
CREATE TABLE IF NOT EXISTS public.clients (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES public.projects(id) ON DELETE CASCADE,
    chat_id BIGINT NOT NULL,
    username TEXT,
    full_name TEXT,
    crm_contact_id TEXT, -- ID во внешней CRM (Bitrix, Amo и т.д.)
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(project_id, chat_id)
);

-- 3. Тред/Сессия (Окно памяти для LangGraph)
CREATE TABLE IF NOT EXISTS public.threads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id UUID REFERENCES public.clients(id) ON DELETE CASCADE,
    status TEXT DEFAULT 'active', -- active, escalation, closed
    summary TEXT, -- Сжатый контекст старой беседы
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 4. Сообщения (Плоская история для MessageGraph)
CREATE TABLE IF NOT EXISTS public.messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    thread_id UUID REFERENCES public.threads(id) ON DELETE CASCADE,
    role TEXT NOT NULL, -- user, assistant, system, tool
    content TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 5. База знаний (RAG)
CREATE TABLE IF NOT EXISTS public.knowledge_base (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES public.projects(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    embedding vector(384), -- Под твой FastEmbed (BGE-Small-EN/RU)
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Индексы для скорости
CREATE INDEX IF NOT EXISTS idx_clients_chat_id ON public.clients(chat_id);
CREATE INDEX IF NOT EXISTS idx_messages_thread_id ON public.messages(thread_id);
CREATE INDEX IF NOT EXISTS idx_knowledge_project_id ON public.knowledge_base(project_id);