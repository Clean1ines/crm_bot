-- Rename metadata column to user_metadata in users table to avoid SQLAlchemy conflict.
ALTER TABLE users RENAME COLUMN metadata TO user_metadata;
