from __future__ import annotations

import inspect

from src.interfaces.http import knowledge


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
