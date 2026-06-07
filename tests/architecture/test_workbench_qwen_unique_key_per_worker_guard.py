from __future__ import annotations

from pathlib import Path


ADAPTER = Path("src/infrastructure/llm/workbench_qwen_json_invocation.py")
HANDLER = Path("src/infrastructure/queue/handlers/workbench_parallel_processing.py")


def test_workbench_pinned_adapter_is_strict_versatile_without_router_or_completion_cap() -> (
    None
):
    source = ADAPTER.read_text(encoding="utf-8")

    required = (
        'WORKBENCH_QWEN_MODEL = "llama-3.3-70b-versatile"',
        "configured_groq_api_keys",
        "AsyncGroq(api_key=selection.key)",
        "max_completion_tokens=None",
        "sanitize_workbench_qwen_json_text",
        're.sub(r"(?is)^\\s*<think>.*?</think>\\s*", "", text, count=1)',
        '"model_routing": "disabled"',
        '"mode": "workbench_qwen_worker_affinity"',
    )
    for marker in required:
        assert marker in source

    forbidden = (
        "_first_groq_api_key",
        "GROQ_API_KEY_",
        "GroqClientRotator",
        "GroqModelRouter",
        "RotatingAsyncGroq",
        "max_completion_tokens=4096",
        "llama-3.1-8b-instant",
        '"qwen/qwen3-32b"',
    )
    for marker in forbidden:
        assert marker not in source


def test_prompt_a_binds_claimed_section_worker_to_qwen_context() -> None:
    source = HANDLER.read_text(encoding="utf-8")

    assert "workbench_qwen_worker_context" in source
    assert "worker_id = command.queue_item.claimed_by_worker_id" in source
    assert "with workbench_qwen_worker_context(worker_id):" in source

    guarded_block = source.split(
        "with workbench_qwen_worker_context(worker_id):",
        1,
    )[1].split("except Exception as exc:", 1)[0]
    assert "generation_result = await self.generator.generate_findings" in guarded_block
