-- Migration: 028_add_analytics_columns.sql
-- Purpose: Add analytics columns to threads table for tracking conversation insights
-- Date: 2026-03-20

-- Add columns to threads table
ALTER TABLE threads
ADD COLUMN IF NOT EXISTS intent TEXT,
ADD COLUMN IF NOT EXISTS lifecycle TEXT,
ADD COLUMN IF NOT EXISTS cta TEXT,
ADD COLUMN IF NOT EXISTS decision TEXT;

-- Create indexes for analytics queries
CREATE INDEX IF NOT EXISTS idx_threads_lifecycle ON threads(lifecycle) WHERE lifecycle IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_threads_intent ON threads(intent) WHERE intent IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_threads_cta ON threads(cta) WHERE cta IS NOT NULL;
