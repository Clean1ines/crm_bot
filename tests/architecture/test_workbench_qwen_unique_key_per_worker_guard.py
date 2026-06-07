from __future__ import annotations

from pathlib import Path


ADAPTER = Path("src/infrastructure/llm/workbench_qwen_json_invocation.py")
HANDLER = Path("src/infrastructure/queue/handlers/workbench_parallel_processing.py")


def test_workbench_prompt_a_target_fallback_chain_keeps_worker_affinity() -> None:
    source = ADAPTER.read_text(encoding="utf-8")

    required = (
        "WORKBENCH_PROMPT_A_FALLBACK_MODELS = (",
        'WORKBENCH_QWEN_MODEL = "qwen/qwen3-32b"',
        '"openai/gpt-oss-120b"',
        '"llama-3.3-70b-versatile"',
        '"meta-llama/llama-4-scout-17b-16e-instruct"',
        "WorkbenchPromptAFallbackLlmJsonInvocationAdapter",
        "configured_groq_api_keys",
        "AsyncGroq(api_key=selection.key)",
        "max_completion_tokens=None",
        'reasoning_effort="none"',
        'reasoning_format="hidden"',
        "sanitize_workbench_qwen_json_text",
        're.sub(r"(?is)^\\s*<think>.*?</think>\\s*", "", text, count=1)',
        '"model_routing": "disabled"',
        '"mode": "workbench_qwen_worker_affinity"',
        "workbench_qwen_worker_key_slot",
    )
    for marker in required:
        assert marker in source

    prompt_a_block = source.split(
        "class WorkbenchPromptAFallbackLlmJsonInvocationAdapter",
        1,
    )[1].split("def sanitize_workbench_qwen_json_text", 1)[0]
    forbidden = (
        "GroqModelRouter",
        "RotatingAsyncGroq",
        "GroqClientRotator",
        "GroqLlmJsonInvocationAdapter.create_default",
        "llama-3.1-8b-instant",
    )
    for marker in forbidden:
        assert marker not in prompt_a_block


def test_prompt_a_binds_claimed_section_worker_to_workbench_context() -> None:
    source = HANDLER.read_text(encoding="utf-8")

    assert "workbench_qwen_worker_context" in source
    assert "worker_id = command.queue_item.claimed_by_worker_id" in source
    assert "with workbench_qwen_worker_context(worker_id):" in source
    assert "WorkbenchPromptAFallbackLlmJsonInvocationAdapter.create_default()" in source
    assert "GroqLlmJsonInvocationAdapter.create_default()" not in source

    guarded_block = source.split(
        "with workbench_qwen_worker_context(worker_id):",
        1,
    )[1].split("except Exception as exc:", 1)[0]
    assert "generation_result = await self.generator.generate_findings" in guarded_block
