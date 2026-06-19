from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from src.contexts.knowledge_workbench.infrastructure.postgres.postgres_draft_claim_compaction_degraded_fallback_decision_repository import (
    PostgresDraftClaimCompactionDegradedFallbackDecisionRepository,
)


@dataclass(slots=True)
class FakeConnection:
    row: dict[str, object] | None
    calls: list[tuple[str, tuple[object, ...]]] = field(default_factory=list)

    async def fetchrow(
        self,
        query: str,
        *args: object,
    ) -> dict[str, object] | None:
        self.calls.append((query, args))
        return self.row


@pytest.mark.asyncio
async def test_loads_only_unresolved_daily_capacity_choice_for_project() -> None:
    connection = FakeConnection(
        {
            "source_command_id": "workflow-command:prepare",
            "source_command_payload": {
                "scheduled_work_item_count": 1,
                "llm_dispatch_preparation": {"requested_items": 1},
            },
            "waiting_payload": {
                "reason": "primary_model_daily_capacity_exhausted",
            },
            "degraded_model_ref": "llama-3.3-70b-versatile",
        }
    )

    decision = await PostgresDraftClaimCompactionDegradedFallbackDecisionRepository(
        connection
    ).load_pending_decision(
        workflow_run_id="workflow-1",
        project_id="project-1",
    )

    assert decision is not None
    assert decision.degraded_model_ref == "llama-3.3-70b-versatile"
    query, args = connection.calls[0]
    assert "NOT EXISTS" in query
    assert "workflow_run.project_id = $2" in query
    assert args[:2] == ("workflow-1", "project-1")
