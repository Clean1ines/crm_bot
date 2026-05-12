from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_stage_h2_frontend_api_exposes_execute_result_actions() -> None:
    source = _read("frontend/src/shared/api/modules/ragEval.ts")

    assert "export interface KnowledgeEditActionExecutionSummary" in source
    assert "export interface RagEvalActionableResult" in source
    assert "executeResultActions(resultId: string)" in source
    assert "/api/rag-eval/results/${encode(resultId)}/actions/execute" in source


def test_stage_h2_rag_eval_page_renders_actionable_results_and_executes_actions() -> (
    None
):
    source = _read("frontend/src/pages/rag-eval/RagEvalPage.tsx")

    assert "const getActionableResults =" in source
    assert "const ActionableResultsPanel:" in source
    assert "const executeActionsMutation = useMutation" in source
    assert "ragEvalApi.executeResultActions(resultId)" in source
    assert "results={actionableResults}" in source
    assert "Safe actions applied" in source


def test_stage_h2_actionable_panel_does_not_render_internal_payload_keys() -> None:
    source = _read("frontend/src/pages/rag-eval/RagEvalPage.tsx")
    start = source.index("const ActionableResultsPanel:")
    end = source.index("const ReportSummaryCard:", start)
    panel = source[start:end]

    assert "answer_text" not in panel
    assert "judge_json" not in panel
    assert "embedding_text" not in panel
    assert "raw evidence" not in panel.lower()
