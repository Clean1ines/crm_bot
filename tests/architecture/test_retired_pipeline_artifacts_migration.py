from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "migrations"
SRC = ROOT / "src"


def _read(path: Path) -> str:
    assert path.exists(), f"missing file: {path}"
    return path.read_text(encoding="utf-8")


def test_migration_088_keeps_stage_work_item_index_but_retires_pipeline_artifacts() -> (
    None
):
    text = _read(MIGRATIONS / "088_create_claim_extraction_stage_work_item_index.sql")

    assert "CREATE TABLE IF NOT EXISTS claim_extraction_stage_work_items" in text
    assert "idx_claim_extraction_stage_work_items_stage" in text
    assert "idx_claim_extraction_stage_work_items_work_item" in text
    assert "pipeline_artifacts no longer exists" in text
    assert "ON pipeline_artifacts" not in text
    assert "idx_pipeline_artifacts_claim_extraction_stage_payload" not in text


def test_stage_progress_counts_draft_claim_observation_provenance_not_pipeline_artifacts() -> (
    None
):
    text = _read(
        SRC
        / "contexts/knowledge_workbench/extraction/infrastructure/postgres/"
        / "postgres_claim_extraction_stage_progress_query.py"
    )

    assert "FROM draft_claim_observation_provenance" in text
    assert "workflow_run_id = $1" in text
    assert "stage_run_id = $2" in text
    assert "FROM pipeline_artifacts" not in text
    assert "artifact_kind LIKE" not in text


def test_current_src_does_not_require_pipeline_artifacts_domain() -> None:
    offenders: list[str] = []

    for path in SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for marker in ("pipeline_artifacts", "PipelineArtifact", "artifact_runtime"):
            if marker in text:
                offenders.append(f"{path.relative_to(ROOT)} contains {marker}")

    assert not offenders, (
        "Current src must not require retired pipeline_artifacts/PipelineArtifact domain:\n"
        + "\n".join(offenders)
    )


def test_later_migrations_do_not_require_pipeline_artifacts_relation() -> None:
    offenders: list[str] = []

    for path in sorted(MIGRATIONS.glob("*.sql")):
        if path.name < "088_create_claim_extraction_stage_work_item_index.sql":
            continue
        text = path.read_text(encoding="utf-8")
        if "pipeline_artifacts" not in text:
            continue

        allowed_drop = path.name == "112_drop_retired_legacy_knowledge_schema.sql" and (
            "DROP TABLE IF EXISTS pipeline_artifacts" in text
        )
        allowed_retired_notice = (
            path.name == "088_create_claim_extraction_stage_work_item_index.sql"
            and ("pipeline_artifacts no longer exists" in text)
        )
        if not (allowed_drop or allowed_retired_notice):
            offenders.append(str(path.relative_to(ROOT)))

    assert not offenders, (
        "Later migrations must not require the retired pipeline_artifacts relation:\n"
        + "\n".join(offenders)
    )


def test_no_generic_placeholder_pipeline_artifacts_schema_restored() -> None:
    migration_text = "\n".join(
        path.read_text(encoding="utf-8") for path in MIGRATIONS.glob("*.sql")
    )

    assert "CREATE TABLE IF NOT EXISTS pipeline_artifacts" not in migration_text
    assert "CREATE TABLE pipeline_artifacts" not in migration_text
    assert "CREATE TABLE IF NOT EXISTS pipeline_artifact_lineage" not in migration_text
    assert "CREATE TABLE pipeline_artifact_lineage" not in migration_text
