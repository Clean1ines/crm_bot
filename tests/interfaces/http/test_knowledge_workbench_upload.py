from __future__ import annotations

import inspect

import pytest
from fastapi import HTTPException

from src.interfaces.http import dependencies, knowledge


def test_upload_declares_overrideable_llm_executor_dependency() -> None:
    parameter = inspect.signature(knowledge.upload_knowledge).parameters["llm_executor"]

    assert getattr(parameter.default, "dependency", None) is (
        knowledge.get_llm_dispatch_executor
    )


def test_upload_boundary_does_not_call_groq_or_executor_directly() -> None:
    source = inspect.getsource(knowledge.upload_knowledge)

    assert "llm_executor=llm_executor" in source
    assert "execute_dispatch(" not in source
    assert "GroqDispatchExecutor" not in source
    assert "GROQ_API_KEY" not in source


def test_llm_dispatch_executor_dependency_fails_fast_without_groq_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for env_name in (
        "GROQ_API_KEY",
        "GROQ_API_KEY2",
        "GROQ_API_KEY3",
        "GROQ_API_KEY4",
    ):
        monkeypatch.delenv(env_name, raising=False)

    with pytest.raises(HTTPException) as exc_info:
        dependencies.get_llm_dispatch_executor()

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "LLM dispatch executor is not configured"
    assert "GROQ_API_KEY" not in str(exc_info.value.detail)
