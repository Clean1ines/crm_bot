from __future__ import annotations

from pathlib import Path

import pytest

from src.infrastructure.llm.groq_llm_json_invocation import GroqLlmJsonInvocationConfig
from src.infrastructure.llm.workbench_qwen_json_invocation import (
    WORKBENCH_PROMPT_A_FALLBACK_MODELS,
    WORKBENCH_QWEN_MODEL,
    WorkbenchPromptAFallbackLlmJsonInvocationAdapter,
    WorkbenchQwenLlmJsonInvocationAdapter,
    sanitize_workbench_qwen_json_text,
    workbench_qwen_worker_key_slot,
)


def test_workbench_qwen_adapter_uses_pinned_qwen_reasoning_off_model() -> None:
    adapter = WorkbenchQwenLlmJsonInvocationAdapter.create_default()

    assert WORKBENCH_QWEN_MODEL == "qwen/qwen3-32b"
    assert adapter.config.default_model == "qwen/qwen3-32b"
    assert adapter.config.max_completion_tokens is None
    assert adapter.config.reasoning_effort == "none"
    assert adapter.config.reasoning_format == "hidden"


def test_workbench_qwen_adapter_normalizes_non_workbench_config() -> None:
    adapter = WorkbenchQwenLlmJsonInvocationAdapter.create_default(
        config=GroqLlmJsonInvocationConfig(
            default_model="llama-3.1-8b-instant",
            temperature=0.2,
            max_completion_tokens=4096,
            reasoning_effort=None,
            reasoning_format=None,
        )
    )

    assert adapter.config.default_model == "qwen/qwen3-32b"
    assert adapter.config.temperature == 0.2
    assert adapter.config.max_completion_tokens is None
    assert adapter.config.reasoning_effort == "none"
    assert adapter.config.reasoning_format == "hidden"


@pytest.mark.parametrize(
    ("raw", "expected"),
    (
        ('<think>reasoning</think>{"claims":[]}', '{"claims":[]}'),
        ('```json\n{"claims": []}\n```', '{"claims": []}'),
        (
            'prefix {"claims":[{"local_ref":"c1"}]} suffix',
            '{"claims":[{"local_ref":"c1"}]}',
        ),
    ),
)
def test_sanitize_workbench_qwen_json_text(raw: str, expected: str) -> None:
    assert sanitize_workbench_qwen_json_text(raw) == expected


def test_workbench_qwen_adapter_parses_json_after_think_block() -> None:
    adapter = WorkbenchQwenLlmJsonInvocationAdapter.create_default()

    assert adapter._loads_json_value('<think>abc</think>{"claims":[]}') == {
        "claims": []
    }


def test_workbench_qwen_worker_key_slot_maps_section_workers_to_four_keys() -> None:
    assert (
        workbench_qwen_worker_key_slot("workbench-parallel-section-1-1", key_count=4)
        == 1
    )
    assert (
        workbench_qwen_worker_key_slot("workbench-parallel-section-1-2", key_count=4)
        == 2
    )
    assert (
        workbench_qwen_worker_key_slot("workbench-parallel-section-1-3", key_count=4)
        == 3
    )
    assert (
        workbench_qwen_worker_key_slot("workbench-parallel-section-1-4", key_count=4)
        == 4
    )
    assert (
        workbench_qwen_worker_key_slot("workbench-parallel-section-1-5", key_count=4)
        == 1
    )


def test_workbench_qwen_worker_key_slot_falls_back_without_worker_context() -> None:
    assert workbench_qwen_worker_key_slot(None, key_count=4) is None
    assert workbench_qwen_worker_key_slot("", key_count=4) is None
    assert workbench_qwen_worker_key_slot("registry-writer", key_count=4) is None


def test_workbench_prompt_a_fallback_adapter_uses_target_chain_reasoning_off() -> None:
    adapter = WorkbenchPromptAFallbackLlmJsonInvocationAdapter.create_default()

    assert WORKBENCH_PROMPT_A_FALLBACK_MODELS == (
        "qwen/qwen3-32b",
        "openai/gpt-oss-120b",
        "llama-3.3-70b-versatile",
        "meta-llama/llama-4-scout-17b-16e-instruct",
    )
    assert adapter.fallback_models == WORKBENCH_PROMPT_A_FALLBACK_MODELS
    assert adapter.config.default_model == "qwen/qwen3-32b"
    assert adapter.config.max_completion_tokens is None
    assert adapter.config.reasoning_effort == "none"
    assert adapter.config.reasoning_format == "hidden"


def test_workbench_prompt_a_fallback_adapter_does_not_expose_global_router_source() -> (
    None
):
    source = Path("src/infrastructure/llm/workbench_qwen_json_invocation.py").read_text(
        encoding="utf-8"
    )

    prompt_a_block = source.split(
        "class WorkbenchPromptAFallbackLlmJsonInvocationAdapter",
        1,
    )[1].split("def sanitize_workbench_qwen_json_text", 1)[0]
    assert "GroqModelRouter" not in prompt_a_block
    assert "RotatingAsyncGroq" not in prompt_a_block
    assert "GroqLlmJsonInvocationAdapter.create_default" not in prompt_a_block
