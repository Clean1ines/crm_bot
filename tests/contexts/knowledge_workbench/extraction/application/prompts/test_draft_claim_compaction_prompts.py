from __future__ import annotations

from pathlib import Path


def test_reduced_claim_rewrite_prompt_contract_is_minimal() -> None:
    prompt = Path(
        "src/contexts/knowledge_workbench/extraction/application/prompts/"
        "reduced_claim_rewrite.txt"
    ).read_text(encoding="utf-8")

    assert "NODE: reduced_claim_rewrite" in prompt
    assert '"compacted_claims"' in prompt
    assert '"key"' in prompt
    assert '"claim"' in prompt
    assert '"triples"' in prompt
    assert "valid JSON only" in prompt
    assert "no text outside JSON" in prompt
    assert "source_claim_refs" not in prompt
    assert "merge_decision" not in prompt
    assert "claim_kind" not in prompt
    assert "granularity" not in prompt
    assert "enriched_claims" not in prompt
    assert '"kind"' not in prompt
