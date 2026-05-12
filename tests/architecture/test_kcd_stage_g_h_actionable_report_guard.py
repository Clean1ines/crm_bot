from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_latest_report_exposes_actionable_results_from_loaded_run_results() -> None:
    source = _read("src/infrastructure/db/repositories/rag_eval_repository.py")

    get_latest_start = source.index("    async def get_latest_report(")
    get_latest_end = source.index("    def _entry_from_row(", get_latest_start)
    get_latest = source[get_latest_start:get_latest_end]

    assert "await self.load_run_results(run_id=run_id)" in get_latest
    assert '"actionable_results"' in get_latest
    assert "_actionable_result_summary(result)" in get_latest
    assert "_is_actionable_result(result)" in get_latest


def test_actionable_result_summary_is_entry_first_and_does_not_expose_raw_payloads() -> (
    None
):
    source = _read("src/infrastructure/db/repositories/rag_eval_repository.py")

    start = source.index("def _actionable_result_summary(")
    end = source.index("\n\nclass RagEvalRepository:", start)
    helper = source[start:end]

    assert '"result_id"' in helper
    assert '"question_id"' in helper
    assert '"expected_entry_ids"' in helper
    assert '"retrieved_entry_ids"' in helper
    assert '"classification"' in helper
    assert '"proposed_actions"' in helper
    assert "_actionable_action_summary(action)" in helper
    assert "action.to_json()" not in helper

    assert '"expected_chunk_ids"' not in helper
    assert '"retrieved_chunks"' not in helper
    assert '"chunk_id"' not in helper
    assert '"retrieved_entries"' not in helper
    assert '"answer_text"' not in helper
    assert '"judge_json"' not in helper
    assert '"embedding_text"' not in helper
