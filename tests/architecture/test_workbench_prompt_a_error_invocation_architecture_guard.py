from pathlib import Path


HANDLER = Path("src/infrastructure/queue/handlers/workbench_parallel_processing.py")


def test_prompt_a_error_path_does_not_use_raw_exception_args_as_invocation() -> None:
    source = HANDLER.read_text()

    assert "def _llm_json_invocation_from_exception(" in source
    assert "isinstance(arg, LlmJsonInvocationResult)" in source
    assert 'getattr(exc, "args", (None,))[0]' not in source
    assert "invocation = _llm_json_invocation_from_exception(exc)" in source
