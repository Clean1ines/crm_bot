from __future__ import annotations

from pathlib import Path

from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_progress import (
    DraftClaimCompactionProgressSummary,
)


ROOT = Path(__file__).resolve().parents[6]


def test_compaction_llm_prompts_do_not_request_granularity_or_exclusion_scope() -> None:
    prompt_paths = (
        ROOT
        / "src/contexts/knowledge_workbench/extraction/application/prompts/draft_claim_compaction.txt",
        ROOT
        / "src/contexts/knowledge_workbench/extraction/application/prompts/enriched_claim_compaction.txt",
        ROOT
        / "src/contexts/knowledge_workbench/extraction/application/prompts/single_draft_claim_enrichment.txt",
    )

    for prompt_path in prompt_paths:
        prompt = prompt_path.read_text(encoding="utf-8")
        assert '"granularity":' not in prompt
        assert '"exclusion_scope":' not in prompt
        assert "NEVER output granularity." in prompt
        assert "NEVER output exclusion_scope." in prompt


def test_compaction_progress_payload_exposes_semantic_component_state() -> None:
    summary = DraftClaimCompactionProgressSummary(
        workflow_run_id="workflow-1",
        group_count=1,
        done_group_count=0,
        waiting_user_model_choice_group_count=0,
        active_group_count=1,
        active_node_count=2,
        pending_comparison_count=0,
        active_component_count=2,
        component_incompatibility_count=1,
    )

    assert summary.to_payload()["active_component_count"] == 2
    assert summary.to_payload()["component_incompatibility_count"] == 1
