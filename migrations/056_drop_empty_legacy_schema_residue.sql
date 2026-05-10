-- Drop empty schema residue after the control-plane/auth/workflow refactors.
--
-- Recon before this migration:
-- - channels: 0 rows, no exact runtime SQL references.
-- - features: 0 rows, no exact runtime SQL references.
-- - workflows: 0 rows, no exact runtime SQL references.
-- - oauth_link_states: 0 rows, no exact runtime SQL references.
--
-- Canonical replacements:
-- - project_channels is the canonical channel table.
-- - runtime/domain feature maps are not persisted in public.features.
-- - current product runtime does not use persisted workflows.
-- - current auth flow does not use oauth_link_states.

DROP TABLE IF EXISTS workflows;
DROP TABLE IF EXISTS features;
DROP TABLE IF EXISTS channels;
DROP TABLE IF EXISTS oauth_link_states;
