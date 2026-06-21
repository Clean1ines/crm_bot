from pathlib import Path


MIGRATION_PATH = Path("migrations/116_create_frontend_workflow_events.sql")


def test_frontend_workflow_events_migration_is_append_only_projection_contract() -> (
    None
):
    migration = MIGRATION_PATH.read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS frontend_workflow_events" in migration
    assert "projection_event_id TEXT PRIMARY KEY" in migration
    assert "source_sequence_number BIGINT NOT NULL" in migration
    assert "projection_version INTEGER NOT NULL" in migration
    assert "payload JSONB NOT NULL" in migration
    assert "CHECK (jsonb_typeof(payload) = 'object')" in migration
    assert "UNIQUE (source_event_id, projection_type, projection_version)" in migration
    assert (
        migration.count(
            "source_sequence_number,\n"
            "        projection_type,\n"
            "        projection_version,\n"
            "        projection_event_id"
        )
        == 3
    )
    assert "BIGSERIAL" not in migration
    assert "REFERENCES workflow_runtime_outbox_events" not in migration
