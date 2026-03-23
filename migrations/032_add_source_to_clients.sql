-- Add source column to clients table to track origin channel (telegram, web_widget, etc.)
ALTER TABLE clients ADD COLUMN source TEXT NOT NULL DEFAULT 'telegram';
