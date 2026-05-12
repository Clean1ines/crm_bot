from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_stage_h_action_execution_api_is_wired_to_application_service() -> None:
    source = _read("src/interfaces/http/rag_eval.py")

    assert '@router.post("/results/{result_id}/actions/execute")' in source
    assert "async def execute_rag_eval_result_actions(" in source
    assert "KnowledgeEditActionService(" in source
    assert "execute_result_actions(" in source
    assert "load_result_action_source(result_id)" in source
    assert "KnowledgeRepository(pool)" in source
    assert "queue_repo=queue_repo" in source


def test_stage_h_action_execution_api_returns_summary_not_internal_payload() -> None:
    source = _read("src/interfaces/http/rag_eval.py")

    start = source.index("async def execute_rag_eval_result_actions(")
    end = source.index(
        '\n\n@router.get("/documents/{document_id}/latest-report")',
        start,
    )
    endpoint = source[start:end]

    assert "source_result_id" in source
    assert "applied_actions" in source
    assert "rejected_actions" in source
    assert "failed_actions" in source
    assert "skipped_actions" in source
    assert "queued_rerun_job_ids" in source

    assert "embedding_text" not in endpoint
    assert "proposed_actions" not in endpoint
    assert "result_payload" not in endpoint
