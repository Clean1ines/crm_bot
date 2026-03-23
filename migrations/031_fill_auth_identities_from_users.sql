-- Migration: Fill auth_identities for users that already have a telegram_id
-- but no corresponding identity record.

INSERT INTO auth_identities (user_id, provider, provider_id, created_at)
SELECT u.id, 'telegram', u.telegram_id::text, now()
FROM users u
WHERE u.telegram_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM auth_identities ai
    WHERE ai.user_id = u.id
      AND ai.provider = 'telegram'
  )
ON CONFLICT (provider, provider_id) DO NOTHING;
