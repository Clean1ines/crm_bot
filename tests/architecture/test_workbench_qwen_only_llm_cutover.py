from __future__ import annotations

from pathlib import Path


HANDLER = Path("src/infrastructure/queue/handlers/workbench_parallel_processing.py")
COMPOSITION = Path("src/interfaces/composition/faq_workbench_parallel_processing.py")
ADAPTER = Path("src/infrastructure/llm/workbench_qwen_json_invocation.py")


def test_workbench_default_llm_invocation_is_pinned_workbench_adapter_legacy_name() -> (
    None
):
    handler = HANDLER.read_text(encoding="utf-8")
    composition = COMPOSITION.read_text(encoding="utf-8")

    for source in (handler, composition):
        assert "WorkbenchQwenLlmJsonInvocationAdapter" in source
        assert "GroqLlmJsonInvocationAdapter.create_default()" not in source

    assert "llama-3.1-8b-instant" not in handler
    assert "llama-3.1-8b-instant" not in composition


def test_workbench_pinned_adapter_uses_qwen_reasoning_off_without_global_router() -> (
    None
):
    source = ADAPTER.read_text(encoding="utf-8")

    assert 'WORKBENCH_QWEN_MODEL = "qwen/qwen3-32b"' in source
    assert '"llama-3.3-70b-versatile"' not in source
    assert "GroqModelRouter" not in source
    assert "RotatingAsyncGroq" not in source
    assert "PRIMARY_CHAIN" not in source
    assert "CHEAP_SMALL_CHAIN" not in source
    assert "max_completion_tokens=None" in source
    assert 'reasoning_effort="none"' in source
    assert 'reasoning_format="hidden"' in source
    assert "workbench_qwen_worker_key_slot" in source
    assert "sanitize_workbench_qwen_json_text" in source
    assert "<think>" in source
    assert "</think>" in source


def test_prompt_a_and_prompt_c_still_share_one_injected_llm_invocation() -> None:
    handler = HANDLER.read_text(encoding="utf-8")
    composition = COMPOSITION.read_text(encoding="utf-8")

    assert "llm_json_invocation=llm_json_invocation" in handler
    assert "llm_invocation=llm_json_invocation" in composition
    assert "workbench_claim_observations" in Path(
        "src/infrastructure/llm/faq_workbench_claim_observations_generator.py"
    ).read_text(encoding="utf-8")
    assert "workbench_fact_registry_canonicalization" in Path(
        "src/infrastructure/llm/faq_workbench_registry_merge_generator.py"
    ).read_text(encoding="utf-8")
