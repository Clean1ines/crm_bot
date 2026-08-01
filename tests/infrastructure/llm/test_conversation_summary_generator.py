from pathlib import Path

import pytest

from src.application.ports.conversation_summary_port import TicketResolutionInput
from src.application.ports.prompt_template_port import PromptTemplateNotFoundError
from src.infrastructure.llm.conversation_summary_generator import (
    PROMPTS_DIR,
    REQUIRED_FIELDS,
    ResponseCompletionConversationSummaryGenerator,
    TicketResolutionSummaryParseError,
    _build_prompt,
    _parse_summary,
)
from src.infrastructure.llm.prompt_template_loader import FilePromptTemplateLoader


def _payload(language: str = "ru") -> TicketResolutionInput:
    return TicketResolutionInput(
        project_id="project-1",
        thread_id="thread-1",
        existing_context_summary="старый контекст",
        messages=[
            {"role": "user", "content": "Нужна цена"},
            {"role": "manager", "content": "Договорились отправить расчёт"},
        ],
        events=[{"event_type": "manager_closed_ticket"}],
        user_memory={"profile": [{"key": "crm", "value": "AmoCRM"}]},
        target_language=language,
    )


def _valid_json() -> str:
    return """
    {
      "summary_text": "Менеджер закрыл обращение.",
      "discussed_questions": ["Цена"],
      "resolved_questions": ["Расчёт отправят"],
      "unresolved_questions": [],
      "manager_decisions": ["Отправить расчёт"],
      "customer_facts": ["Клиент интересуется ценой"],
      "business_commitments": ["Отправить расчёт"]
    }
    """


def test_build_prompt_loads_utf8_template_without_mojibake() -> None:
    prompt = _build_prompt(_payload())

    assert "?" * 3 not in prompt
    assert "\ufffd" not in prompt
    assert "Не выдумывай решения" in prompt
    assert "manager_decisions можно брать только из сообщений менеджера" in prompt
    for field in REQUIRED_FIELDS:
        assert field in prompt


def test_prompt_loader_uses_language_fallback() -> None:
    prompt = _build_prompt(_payload("en"))

    assert "Ты формируешь итог закрытого обращения" in prompt
    assert (
        "Write summary_text and all structured string values in language: en." in prompt
    )


def test_prompt_loader_missing_file_is_typed_error(tmp_path: Path) -> None:
    loader = FilePromptTemplateLoader(tmp_path)

    with pytest.raises(PromptTemplateNotFoundError):
        loader.load("ticket_resolution_summary", language="ru")


def test_prompt_file_exists_at_production_path() -> None:
    assert (PROMPTS_DIR / "ticket_resolution_summary.ru.txt").is_file()


def test_valid_json_parses_summary() -> None:
    summary = _parse_summary(_valid_json())

    assert summary.summary_text == "Менеджер закрыл обращение."
    assert summary.manager_decisions == ["Отправить расчёт"]


@pytest.mark.parametrize(
    "content",
    [
        "not json",
        "[]",
        '{"discussed_questions":[],"resolved_questions":[],"unresolved_questions":[],"manager_decisions":[],"customer_facts":[],"business_commitments":[]}',
        '{"summary_text":"ok","discussed_questions":"bad","resolved_questions":[],"unresolved_questions":[],"manager_decisions":[],"customer_facts":[],"business_commitments":[]}',
    ],
)
def test_invalid_summary_output_raises_typed_parse_error(content: str) -> None:
    with pytest.raises(TicketResolutionSummaryParseError):
        _parse_summary(content)


def test_fenced_valid_json_parses_summary() -> None:
    summary = _parse_summary(f"```json\n{_valid_json()}\n```")

    assert summary.summary_text == "Менеджер закрыл обращение."


@pytest.mark.asyncio
async def test_generator_uses_completion_client_and_strict_parser() -> None:
    class Completion:
        async def complete(self, prompt: str, **kwargs):
            assert "Recent messages" in prompt
            assert kwargs["target_language"] == "ru"
            return _valid_json()

    generator = ResponseCompletionConversationSummaryGenerator(
        completion_client=Completion()
    )

    summary = await generator.generate_ticket_resolution(_payload())

    assert summary.summary_text == "Менеджер закрыл обращение."
