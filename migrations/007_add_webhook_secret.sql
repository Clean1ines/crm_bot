-- Add webhook_secret column to projects table for verifying incoming webhook authenticity.
ALTER TABLE projects ADD COLUMN IF NOT EXISTS webhook_secret TEXT;
