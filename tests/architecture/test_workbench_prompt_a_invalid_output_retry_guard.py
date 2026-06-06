from pathlib import Path


TERMINAL = Path(
    "src/infrastructure/queue/handlers/workbench_parallel_processing_terminal.py"
)
GENERATOR = Path("src/infrastructure/llm/faq_workbench_claim_observations_generator.py")


def test_prompt_a_invalid_output_contract_failures_are_retryable() -> None:
    source = TERMINAL.read_text(encoding="utf-8")

    assert "TransientJobError" in source
    assert "_is_retryable_prompt_a_output_contract_failure" in source
    assert "retryable Prompt A output contract failure" in source
    assert "requires non-empty string evidence_block" in source
    assert "unsupported predicate" in source
    assert "unsupported relation" in source


def test_prompt_a_parser_does_not_autofix_missing_evidence_block() -> None:
    source = GENERATOR.read_text(encoding="utf-8")

    assert '"evidence_block": self._required_str(' in source
    assert '"evidence_block": self._evidence_block' not in source
    assert "def _evidence_block(" not in source
    assert "return claim.strip()" not in source
