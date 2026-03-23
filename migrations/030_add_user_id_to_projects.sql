-- Migration: Add user_id to projects for linking with users table.
-- Step 1: Add the column (nullable initially).
ALTER TABLE projects ADD COLUMN IF NOT EXISTS user_id UUID REFERENCES users(id);

-- Step 2: Fill user_id for projects where owner_id matches a telegram identity.
-- This assumes owner_id contains either:
--   - a telegram_id (numeric string) for projects created via bot, or
--   - a UUID (string) for projects created via web (but web projects don't exist yet).
UPDATE projects p
SET user_id = u.id
FROM auth_identities ai
JOIN users u ON u.id = ai.user_id
WHERE ai.provider = 'telegram'
  AND ai.provider_id = p.owner_id
  AND p.user_id IS NULL;

-- Optional: if any projects still have no user_id and owner_id looks like a UUID,
-- we could assume it's already a user_id, but for now leave as NULL.
