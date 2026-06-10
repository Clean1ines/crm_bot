from __future__ import annotations

from pathlib import Path


BUILDER_PATH = Path(
    "src/contexts/llm_runtime/infrastructure/providers/groq/"
    "groq_chat_request_builder.py",
)
BUILDER_TEST_PATH = Path(
    "tests/contexts/llm_runtime/infrastructure/providers/groq/"
    "test_groq_chat_request_builder.py",
)
MODEL_ROUTE_CATALOG_PATH = Path(
    "src/contexts/llm_runtime/domain/capacity/llm_model_route_catalog.py",
)


def test_groq_request_builder_execution_settings_required_markers_exist() -> None:
    source = "\n".join(
        (
            BUILDER_PATH.read_text(encoding="utf-8"),
            BUILDER_TEST_PATH.read_text(encoding="utf-8"),
            MODEL_ROUTE_CATALOG_PATH.read_text(encoding="utf-8"),
        ),
    )

    required = (
        "LlmModelExecutionSettings",
        "execution_settings",
        "reasoning_enabled",
        "reasoning_effort",
        "default_groq_llm_model_route_catalog",
        "qwen/qwen3-32b",
    )
    for marker in required:
        assert marker in source


def test_groq_request_builder_does_not_call_http_or_read_env() -> None:
    source = BUILDER_PATH.read_text(encoding="utf-8")

    forbidden = (
        "os.environ",
        "GROQ_API_KEY",
        "Authorization",
        "import httpx",
        "from httpx",
        "httpx.",
        "import requests",
        "from requests",
        "requests.",
        "AsyncGroq",
    )
    for marker in forbidden:
        assert marker not in source
