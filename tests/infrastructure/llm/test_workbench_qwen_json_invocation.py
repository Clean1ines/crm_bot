from __future__ import annotations

import pytest

from src.infrastructure.llm.groq_llm_json_invocation import GroqLlmJsonInvocationConfig
from src.infrastructure.llm.workbench_qwen_json_invocation import (
    WORKBENCH_QWEN_MODEL,
    WorkbenchQwenLlmJsonInvocationAdapter,
    sanitize_workbench_qwen_json_text,
    workbench_qwen_worker_key_slot,
)


def test_workbench_qwen_adapter_uses_fixed_qwen_model() -> None:
    adapter = WorkbenchQwenLlmJsonInvocationAdapter(
        client=object(),
        config=GroqLlmJsonInvocationConfig(
            default_model=WORKBENCH_QWEN_MODEL,
            max_completion_tokens=None,
        ),
    )

    assert adapter.config.default_model == "qwen/qwen3-32b"


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
    adapter = WorkbenchQwenLlmJsonInvocationAdapter(
        client=object(),
        config=GroqLlmJsonInvocationConfig(
            default_model=WORKBENCH_QWEN_MODEL,
            max_completion_tokens=None,
        ),
    )

    assert adapter._loads_json_value('<think>abc</think>{"claims":[]}') == {
        "claims": []
    }


def test_workbench_qwen_worker_key_slot_maps_section_workers_to_unique_keys() -> None:
    assert (
        workbench_qwen_worker_key_slot(
            "workbench-parallel-section-1-1",
            key_count=3,
        )
        == 1
    )
    assert (
        workbench_qwen_worker_key_slot(
            "workbench-parallel-section-1-2",
            key_count=3,
        )
        == 2
    )
    assert (
        workbench_qwen_worker_key_slot(
            "workbench-parallel-section-1-3",
            key_count=3,
        )
        == 3
    )


def test_workbench_qwen_worker_key_slot_falls_back_without_worker_context() -> None:
    assert workbench_qwen_worker_key_slot(None, key_count=3) is None
    assert workbench_qwen_worker_key_slot("", key_count=3) is None
    assert workbench_qwen_worker_key_slot("registry-writer", key_count=3) is None
