from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from src.application.ports.conversation_summary_port import (
    ConversationSummaryGeneratorPort,
    TicketResolutionInput,
    TicketResolutionSummary,
)
from src.application.ports.text_completion_port import TextCompletionPort
from src.infrastructure.llm.completion_client import GroqTextCompletionClient
from src.infrastructure.llm.prompt_template_loader import FilePromptTemplateLoader


PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
PROMPT_STEM = "ticket_resolution_summary"
SUMMARY_TEXT_LIMIT = 1200
STRUCTURED_ITEM_LIMIT = 240
STRUCTURED_LIST_LIMIT = 8
REQUIRED_FIELDS = (
    "summary_text",
    "discussed_questions",
    "resolved_questions",
    "unresolved_questions",
    "manager_decisions",
    "customer_facts",
    "business_commitments",
)


class TicketResolutionSummaryParseError(ValueError):
    pass


class ResponseCompletionConversationSummaryGenerator(ConversationSummaryGeneratorPort):
    def __init__(
        self,
        *,
        completion_client: TextCompletionPort | None = None,
        prompt_loader: FilePromptTemplateLoader | None = None,
    ) -> None:
        self.completion_client = completion_client or GroqTextCompletionClient()
        self.prompt_loader = prompt_loader or FilePromptTemplateLoader(PROMPTS_DIR)

    async def generate_ticket_resolution(
        self, payload: TicketResolutionInput
    ) -> TicketResolutionSummary:
        prompt = _build_prompt(payload, loader=self.prompt_loader)
        content = await self.completion_client.complete(
            prompt,
            target_language=payload.target_language,
            max_tokens=700,
            temperature=0.2,
        )
        return _parse_summary(content)


def _build_prompt(
    payload: TicketResolutionInput,
    *,
    loader: FilePromptTemplateLoader | None = None,
) -> str:
    template = (loader or FilePromptTemplateLoader(PROMPTS_DIR)).load(
        PROMPT_STEM,
        language=payload.target_language,
    )
    values = {
        "target_language": payload.target_language,
        "existing_context_summary": payload.existing_context_summary or "[]",
        "messages": json.dumps(payload.messages[-30:], ensure_ascii=False),
        "events": json.dumps(payload.events[-30:], ensure_ascii=False),
        "user_memory": json.dumps(payload.user_memory, ensure_ascii=False),
    }
    for key, value in values.items():
        template = template.replace(f"{{{{{key}}}}}", value)
    return template


def _parse_summary(content: str) -> TicketResolutionSummary:
    payload = _json_object_from_content(content)
    missing = [field for field in REQUIRED_FIELDS if field not in payload]
    if missing:
        raise TicketResolutionSummaryParseError(
            f"Missing ticket resolution fields: {', '.join(missing)}"
        )

    summary_text = _bounded_required_text(payload.get("summary_text"))
    return TicketResolutionSummary(
        summary_text=summary_text,
        discussed_questions=_required_string_list(payload.get("discussed_questions")),
        resolved_questions=_required_string_list(payload.get("resolved_questions")),
        unresolved_questions=_required_string_list(payload.get("unresolved_questions")),
        manager_decisions=_required_string_list(payload.get("manager_decisions")),
        customer_facts=_required_string_list(payload.get("customer_facts")),
        business_commitments=_required_string_list(payload.get("business_commitments")),
    )


def _json_object_from_content(content: str) -> Mapping[str, object]:
    text = _strip_json_fence(content)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise TicketResolutionSummaryParseError(
            "Invalid ticket resolution JSON"
        ) from exc
    if not isinstance(payload, Mapping):
        raise TicketResolutionSummaryParseError(
            "Ticket resolution output must be a JSON object"
        )
    return payload


def _strip_json_fence(content: str) -> str:
    text = content.strip()
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if len(lines) < 3 or not lines[-1].strip().startswith("```"):
        return text
    first = lines[0].strip().lower()
    if first not in {"```", "```json"}:
        return text
    return "\n".join(lines[1:-1]).strip()


def _bounded_required_text(value: object) -> str:
    if not isinstance(value, str):
        raise TicketResolutionSummaryParseError("summary_text must be a string")
    text = " ".join(value.split())[:SUMMARY_TEXT_LIMIT].strip()
    if not text:
        raise TicketResolutionSummaryParseError("summary_text must not be empty")
    return text


def _required_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        raise TicketResolutionSummaryParseError(
            "Structured ticket resolution fields must be arrays"
        )
    result: list[str] = []
    for item in value[:STRUCTURED_LIST_LIMIT]:
        if not isinstance(item, str):
            raise TicketResolutionSummaryParseError(
                "Structured ticket resolution field items must be strings"
            )
        text = " ".join(item.split())[:STRUCTURED_ITEM_LIMIT].strip()
        if text:
            result.append(text)
    return result
