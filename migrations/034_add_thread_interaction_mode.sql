-- Add interaction_mode to threads to distinguish normal/demo/manual_review/handoff_pending
ALTER TABLE threads ADD COLUMN interaction_mode TEXT NOT NULL DEFAULT 'normal';
CREATE INDEX idx_threads_interaction_mode ON threads(interaction_mode);
