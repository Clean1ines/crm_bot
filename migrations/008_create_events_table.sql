-- Migration: 008_create_events_table
-- Purpose: Event Store foundation for agent runtime
-- Creates the events table for event-sourced conversation tracking

CREATE TABLE IF NOT EXISTS events (
    id BIGSERIAL PRIMARY KEY,
    stream_id UUID NOT NULL,
    project_id UUID NOT NULL,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- Index for loading conversation streams
CREATE INDEX IF NOT EXISTS idx_events_stream ON events(stream_id, created_at);

-- Index for project-level analytics
CREATE INDEX IF NOT EXISTS idx_events_project_type ON events(project_id, event_type);

-- Index for time-based queries
CREATE INDEX IF NOT EXISTS idx_events_created_at ON events(created_at);

-- Foreign key to projects (with cascade delete)
ALTER TABLE events 
ADD CONSTRAINT fk_events_project 
FOREIGN KEY (project_id) 
REFERENCES projects(id) 
ON DELETE CASCADE;

-- Comment for documentation
COMMENT ON TABLE events IS 'Event Store for agent conversations. All state changes are recorded as events.';
COMMENT ON COLUMN events.stream_id IS 'Conversation/thread ID - groups events by dialogue';
COMMENT ON COLUMN events.event_type IS 'Type of event: message_received, ai_replied, tool_called, ticket_created, etc.';
COMMENT ON COLUMN events.payload IS 'Event-specific data in JSON format';
