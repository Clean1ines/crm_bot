from __future__ import annotations

from pathlib import Path


def test_full_document_rag_eval_resumes_existing_dataset_before_generation() -> None:
    root = Path(__file__).resolve().parents[2]
    source = (root / "src/infrastructure/queue/handlers/rag_eval.py").read_text(
        encoding="utf-8"
    )

    assert "_resume_existing_rag_eval_dataset" in source
    assert "get_latest_ready_dataset_with_questions" in source
    assert "get_latest_resumable_run" in source
    assert "load_run_results" in source
    assert "run_progress_callback=None" in source
    assert "run_metrics_callback=_on_run_metrics" in source
    assert "retrieval_concurrency=retrieval_concurrency" in source
    assert "asyncio.as_completed(tasks)" in source


def test_rag_eval_repository_can_load_resume_artifacts() -> None:
    root = Path(__file__).resolve().parents[2]
    source = (
        root / "src/infrastructure/db/repositories/rag_eval_repository.py"
    ).read_text(encoding="utf-8")

    assert "async def get_latest_ready_dataset_with_questions" in source
    assert "async def get_latest_resumable_run" in source
    assert "async def load_run_results" in source
