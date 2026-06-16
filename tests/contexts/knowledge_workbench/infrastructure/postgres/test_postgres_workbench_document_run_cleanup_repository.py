from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]


def test_cleanup_repository_has_dependency_safe_delete_order() -> None:
    content = (
        ROOT / "src/contexts/knowledge_workbench/infrastructure/postgres/"
        "postgres_workbench_document_run_cleanup_repository.py"
    ).read_text(encoding="utf-8")

    method_start = content.index("    async def delete_document_run(")
    method_end = content.index("\n\ndef _delete_count", method_start)
    method_body = content[method_start:method_end]

    ordered_markers = [
        "_delete_runtime_embeddings",
        "_delete_runtime_entries",
        "_delete_curation_items",
        "_delete_compaction_artifacts",
        "_delete_draft_claims",
        "_delete_execution_work_items",
        "_delete_timeline_entries",
        "_delete_saga_runs",
        "_delete_source_units",
        "_delete_source_document",
        "_delete_workbench_document",
    ]

    last_index = -1
    for marker in ordered_markers:
        index = method_body.find(marker)
        assert index > last_index, marker
        last_index = index


def test_cleanup_repository_collects_cross_runtime_refs_before_delete() -> None:
    content = (
        ROOT / "src/contexts/knowledge_workbench/infrastructure/postgres/"
        "postgres_workbench_document_run_cleanup_repository.py"
    ).read_text(encoding="utf-8")

    assert "draft_claim_observation_provenance" in content
    assert "workflow_runtime_timeline_entries" in content
    assert "execution_work_items" in content
    assert "llm_task_id" in content
    assert "llm_attempt_id" in content
