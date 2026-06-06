from pathlib import Path


GENERATOR = Path("src/infrastructure/llm/faq_workbench_claim_observations_generator.py")
TERMINAL = Path(
    "src/infrastructure/queue/handlers/workbench_parallel_processing_terminal.py"
)


def test_prompt_a_does_not_fallback_missing_evidence_block_to_claim() -> None:
    source = GENERATOR.read_text(encoding="utf-8")

    assert '"evidence_block": self._required_str(' in source
    assert '"evidence_block": self._evidence_block' not in source
    assert "def _evidence_block(" not in source
    assert "return claim.strip()" not in source


def test_prompt_a_contract_failures_are_retryable_at_terminal_boundary() -> None:
    source = TERMINAL.read_text(encoding="utf-8")

    assert "TransientJobError" in source
    assert "_is_retryable_prompt_a_contract_failure" in source
    assert "retryable Prompt A output contract failure" in source
    assert "claim observation" in source
