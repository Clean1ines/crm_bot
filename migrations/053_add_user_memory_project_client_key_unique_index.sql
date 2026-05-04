-- Ensure MemoryRepository.set() UPSERT has a matching conflict target.
-- Runtime symptom:
-- asyncpg.exceptions.InvalidColumnReferenceError:
-- there is no unique or exclusion constraint matching the ON CONFLICT specification

CREATE UNIQUE INDEX IF NOT EXISTS idx_user_memory_project_client_key_unique
    ON user_memory(project_id, client_id, key);
