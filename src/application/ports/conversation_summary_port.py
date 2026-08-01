from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol, TypedDict


TicketResolutionStatus = Literal["pending", "generated", "edited", "failed", "missing"]
TicketResolutionSource = Literal["llm", "manager"] | None


class TicketResolutionPayload(TypedDict, total=False):
    summary_text: str
    status: TicketResolutionStatus
    source: TicketResolutionSource
    version: int
    generated_at: str | None
    updated_at: str
    discussed_questions: list[str]
    resolved_questions: list[str]
    unresolved_questions: list[str]
    manager_decisions: list[str]
    customer_facts: list[str]
    business_commitments: list[str]
    error_type: str


@dataclass(frozen=True, slots=True)
class TicketResolutionSummary:
    summary_text: str
    discussed_questions: list[str] = field(default_factory=list)
    resolved_questions: list[str] = field(default_factory=list)
    unresolved_questions: list[str] = field(default_factory=list)
    manager_decisions: list[str] = field(default_factory=list)
    customer_facts: list[str] = field(default_factory=list)
    business_commitments: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class TicketResolutionInput:
    project_id: str
    thread_id: str
    existing_context_summary: str | None
    messages: list[dict[str, object]]
    events: list[dict[str, object]]
    user_memory: dict[str, object]
    target_language: str = "ru"


class ConversationSummaryGeneratorPort(Protocol):
    async def generate_ticket_resolution(
        self, payload: TicketResolutionInput
    ) -> TicketResolutionSummary: ...
