from pathlib import Path


def test_conversation_summary_generator_does_not_import_agent() -> None:
    source = Path("src/infrastructure/llm/conversation_summary_generator.py").read_text(
        encoding="utf-8"
    )

    assert "src.agent" not in source
    assert "complete_response_prompt" not in source


def test_conversation_summary_generator_has_no_inline_prompt_literal() -> None:
    source = Path("src/infrastructure/llm/conversation_summary_generator.py").read_text(
        encoding="utf-8"
    )

    assert "Ты формируешь итог закрытого обращения" not in source
    assert "manager_decisions можно брать" not in source


def test_ticket_resolution_prompt_resource_is_packaged_by_docker_context() -> None:
    prompt = Path("src/infrastructure/llm/prompts/ticket_resolution_summary.ru.txt")
    dockerignore = Path(".dockerignore").read_text(encoding="utf-8")
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")

    assert prompt.is_file()
    assert "src/infrastructure/llm/prompts" not in dockerignore
    assert "COPY" in dockerfile
