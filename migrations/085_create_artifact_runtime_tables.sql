-- Canonical Artifact Runtime persistence.
-- Payload is opaque JSONB. Artifact Runtime does not interpret Workbench semantics.

CREATE TABLE IF NOT EXISTS pipeline_artifacts (
    artifact_ref text PRIMARY KEY,
    artifact_kind text NOT NULL,
    status text NOT NULL,
    visibility text NOT NULL,
    retention_policy_kind text NOT NULL,
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,

    CONSTRAINT chk_pipeline_artifacts_ref_non_empty
        CHECK (length(trim(artifact_ref)) > 0),

    CONSTRAINT chk_pipeline_artifacts_kind_non_empty
        CHECK (length(trim(artifact_kind)) > 0),

    CONSTRAINT chk_pipeline_artifacts_status
        CHECK (
            status IN (
                'stored',
                'validated',
                'rejected',
                'superseded',
                'expired'
            )
        ),

    CONSTRAINT chk_pipeline_artifacts_visibility_non_empty
        CHECK (length(trim(visibility)) > 0),

    CONSTRAINT chk_pipeline_artifacts_retention_policy_non_empty
        CHECK (length(trim(retention_policy_kind)) > 0),

    CONSTRAINT chk_pipeline_artifacts_payload_is_object
        CHECK (jsonb_typeof(payload) = 'object'),

    CONSTRAINT chk_pipeline_artifacts_updated_after_created
        CHECK (updated_at >= created_at)
);

CREATE TABLE IF NOT EXISTS pipeline_artifact_lineage (
    artifact_ref text NOT NULL REFERENCES pipeline_artifacts(artifact_ref) ON DELETE CASCADE,
    parent_artifact_ref text NOT NULL REFERENCES pipeline_artifacts(artifact_ref) ON DELETE CASCADE,

    CONSTRAINT pk_pipeline_artifact_lineage
        PRIMARY KEY (artifact_ref, parent_artifact_ref),

    CONSTRAINT chk_pipeline_artifact_lineage_not_self
        CHECK (artifact_ref <> parent_artifact_ref)
);

CREATE INDEX IF NOT EXISTS idx_pipeline_artifacts_kind_status
    ON pipeline_artifacts (artifact_kind, status, updated_at);

CREATE INDEX IF NOT EXISTS idx_pipeline_artifacts_retention
    ON pipeline_artifacts (retention_policy_kind, updated_at);

CREATE INDEX IF NOT EXISTS idx_pipeline_artifact_lineage_parent
    ON pipeline_artifact_lineage (parent_artifact_ref);
