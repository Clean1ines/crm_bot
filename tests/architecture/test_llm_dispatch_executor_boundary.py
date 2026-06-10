from __future__ import annotations

from pathlib import Path


PORT_PATH = Path(
    "src/contexts/llm_runtime/application/ports/llm_dispatch_executor_port.py",
)


def test_llm_dispatch_executor_required_markers_exist() -> None:
    source = PORT_PATH.read_text(encoding="utf-8")

    required = (
        "LlmDispatchExecutorPort",
        "LlmDispatchExecutionInput",
        "LlmDispatchExecutionResult",
        "LlmDispatchExecutionStatus",
        "llm_execution_settings",
        "execute_dispatch",
    )
    for marker in required:
        assert marker in source


def test_llm_dispatch_executor_port_remains_boundary_only() -> None:
    source = PORT_PATH.read_text(encoding="utf-8")

    forbidden = (
        "Groq",
        "qwen",
        "provider",
        "account_ref",
        "model_ref",
        "httpx",
        "requests",
        "os.environ",
        "GROQ_API_KEY",
        "execution_runtime",
        "knowledge_workbench",
        "artifact_runtime",
    )
    for marker in forbidden:
        assert marker not in source
