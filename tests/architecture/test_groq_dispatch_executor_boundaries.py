from __future__ import annotations

from pathlib import Path


EXECUTOR_PATH = Path(
    "src/contexts/llm_runtime/infrastructure/providers/groq/groq_dispatch_executor.py",
)


def test_groq_dispatch_executor_required_markers_exist() -> None:
    source = EXECUTOR_PATH.read_text(encoding="utf-8")

    required = (
        "GroqDispatchExecutor",
        "LlmDispatchExecutorPort",
        "execute_dispatch",
        "LlmDispatchExecutionInput",
        "LlmDispatchExecutionResult",
        "GroqChatRequestBuilder",
        "GroqProviderResponseMapper",
        "GroqTransportPort",
        "llm_execution_settings",
        "provider_messages",
    )
    for marker in required:
        assert marker in source


def test_groq_dispatch_executor_does_not_use_legacy_or_cross_context_paths() -> None:
    source = EXECUTOR_PATH.read_text(encoding="utf-8")

    forbidden = (
        "LlmProviderPort",
        "ExecuteLlmTask",
        "ExecuteAndRecordLlmTask",
        "os.environ",
        "GROQ_API_KEY",
        "Authorization",
        "AsyncGroq",
        "httpx",
        "knowledge_workbench",
        "execution_runtime",
        "artifact_runtime",
    )
    for marker in forbidden:
        assert marker not in source

    assert "import requests" not in source
    assert "from requests" not in source
