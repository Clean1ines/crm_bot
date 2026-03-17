-- Migration: 009_create_workflow_templates
-- Purpose: Template system for pre-built workflow graphs
-- Allows projects to start with ready-made configurations

CREATE TABLE IF NOT EXISTS workflow_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    graph_json JSONB NOT NULL,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- Index for active template lookup
CREATE INDEX IF NOT EXISTS idx_templates_active ON workflow_templates(is_active) WHERE is_active = true;

-- Index for slug lookup
CREATE INDEX IF NOT EXISTS idx_templates_slug ON workflow_templates(slug);

-- Comment for documentation
COMMENT ON TABLE workflow_templates IS 'Pre-built workflow templates for quick project setup';
COMMENT ON COLUMN workflow_templates.slug IS 'Unique identifier for template (e.g., "support", "leads", "orders")';
COMMENT ON COLUMN workflow_templates.graph_json IS 'LangGraph-compatible graph definition';

-- Insert default templates
INSERT INTO workflow_templates (slug, name, description, graph_json) VALUES
('support', 'Поддержка клиентов', 'Базовый бот для ответов на вопросы клиентов с RAG и эскалацией', 
 '{"nodes":[{"id":"start","type":"start"},{"id":"rag","type":"rag_search"},{"id":"ai","type":"ai_reply"},{"id":"escalate","type":"escalate"}],"edges":[["start","rag"],["rag","ai"],["ai","escalate"]],"entry_point":"start"}'),
('leads', 'Генерация лидов', 'Бот для сбора контактных данных и создания лидов в CRM', 
 '{"nodes":[{"id":"start","type":"start"},{"id":"classify","type":"ai_classifier"},{"id":"collect","type":"ai_reply"},{"id":"crm","type":"tool_call"}],"edges":[["start","classify"],["classify","collect"],["collect","crm"]],"entry_point":"start"}'),
('orders', 'Приём заказов', 'Бот для обработки заказов товаров/услуг', 
 '{"nodes":[{"id":"start","type":"start"},{"id":"menu","type":"ai_reply"},{"id":"order","type":"tool_call"},{"id":"confirm","type":"ai_reply"}],"edges":[["start","menu"],["menu","order"],["order","confirm"]],"entry_point":"start"}');
