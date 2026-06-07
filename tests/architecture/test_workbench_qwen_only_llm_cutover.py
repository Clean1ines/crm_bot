from __future__ import annotations

from pathlib import Path


ADAPTER = Path("src/infrastructure/llm/workbench_qwen_json_invocation.py")
HANDLER = Path("src/infrastructure/queue/handlers/workbench_parallel_processing.py")


def test_workbench_prompt_a_uses_target_fallback_adapter_not_global_router() -> None:
    adapter_source = ADAPTER.read_text(encoding="utf-8")
    handler_source = HANDLER.read_text(encoding="utf-8")

    assert "WorkbenchPromptAFallbackLlmJsonInvocationAdapter" in adapter_source
    assert "WORKBENCH_PROMPT_A_FALLBACK_MODELS" in adapter_source
    assert "WorkbenchPromptAFallbackLlmJsonInvocationAdapter" in handler_source
    assert "WorkbenchPromptAFallbackLlmJsonInvocationAdapter.create_default()" in (
        handler_source
    )

    prompt_a_block = adapter_source.split(
        "class WorkbenchPromptAFallbackLlmJsonInvocationAdapter",
        1,
    )[1].split("def sanitize_workbench_qwen_json_text", 1)[0]
    assert "GroqModelRouter" not in prompt_a_block
    assert "RotatingAsyncGroq" not in prompt_a_block
    assert "GroqLlmJsonInvocationAdapter.create_default" not in prompt_a_block


def test_workbench_prompt_a_fallback_chain_order_is_explicit() -> None:
    source = ADAPTER.read_text(encoding="utf-8")

    qwen_index = source.index("WORKBENCH_QWEN_MODEL,")
    gpt_oss_index = source.index('"openai/gpt-oss-120b"')
    versatile_index = source.index('"llama-3.3-70b-versatile"')
    scout_index = source.index('"meta-llama/llama-4-scout-17b-16e-instruct"')

    assert qwen_index < gpt_oss_index < versatile_index < scout_index


def test_workbench_prompt_a_generator_contains_validation_retry_contract() -> None:
    source = Path(
        "src/infrastructure/llm/faq_workbench_claim_observations_generator.py"
    ).read_text(encoding="utf-8")

    assert "_generate_findings_with_fallback" in source
    assert "_validate_claim_observations_against_section" in source
    assert "_normalized_evidence_block" in source
    assert "_validate_russian_text_field" in source
    assert "evidence_block must exactly match section text" in source
    assert "must match source language" in source
    assert "contains foreign terms" in source
    assert "not present in source section" in source
