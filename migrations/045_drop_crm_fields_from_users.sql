-- Migration 045: Remove CRM-only fields from platform users.
--
-- Email remains on users because it is a platform identity/auth field.
-- Company and phone belong to project-scoped clients/contacts.

ALTER TABLE users
    DROP COLUMN IF EXISTS company,
    DROP COLUMN IF EXISTS phone;
