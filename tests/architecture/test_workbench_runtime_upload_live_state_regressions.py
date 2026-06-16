from __future__ import annotations

from pathlib import Path


def test_source_units_jsonb_values_are_serialized_before_asyncpg_execute() -> None:
    source = Path(
        "src/contexts/knowledge_workbench/source_management/infrastructure/postgres/"
        "postgres_source_management_repository.py",
    ).read_text(encoding="utf-8")

    assert "import json" in source
    assert "json.dumps(list(unit.heading_path.parts))" in source
    assert "json.dumps(" in source
    assert "list(unit.heading_path.parts)," not in source


def test_workflow_live_state_does_not_filter_observations_by_missing_workflow_run_id() -> (
    None
):
    source = Path(
        "src/interfaces/composition/faq_workbench_workflow_live_state.py",
    ).read_text(encoding="utf-8")

    assert "FROM draft_claim_observations AS o" in source
    assert "JOIN source_units AS u" in source
    assert "u.unit_ref = o.source_unit_ref" in source
    assert "WHERE u.document_ref = $2" in source
    assert "WHERE o.workflow_run_id = $3" not in source
