from __future__ import annotations

import pytest

from src.infrastructure.llm.groq_llm_json_invocation import GroqLlmJsonInvocationConfig
from src.infrastructure.llm.workbench_qwen_json_invocation import (
    WORKBENCH_QWEN_MODEL,
    WorkbenchQwenLlmJsonInvocationAdapter,
    sanitize_workbench_qwen_json_text,
)


def test_workbench_qwen_adapter_uses_fixed_qwen_model() -> None:
    adapter = WorkbenchQwenLlmJsonInvocationAdapter(
        client=object(),
        config=GroqLlmJsonInvocationConfig(
            default_model=WORKBENCH_QWEN_MODEL,
            max_completion_tokens=4096,
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
            max_completion_tokens=4096,
        ),
    )

    assert adapter._loads_json_value('<think>abc</think>{"claims":[]}') == {
        "claims": []
    }
