from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_cluster_preview import (
    DraftClaimClusterPreview,
    DraftClaimClusterPreviewClaim,
    DraftClaimClusterPreviewGroup,
)
from src.contexts.knowledge_workbench.extraction.infrastructure.postgres.postgres_draft_claim_cluster_preview_repository import (
    PostgresDraftClaimClusterPreviewRepository,
)


def _now() -> datetime:
    return datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)


def _preview(*, claim: str = "Product supports refunds.") -> DraftClaimClusterPreview:
    return DraftClaimClusterPreview(
        workflow_run_id="workflow-1",
        groups=(
            DraftClaimClusterPreviewGroup(
                group_ref="group-1",
                claims=(
                    DraftClaimClusterPreviewClaim(
                        key="refund_support",
                        claim=claim,
                        claim_kind="capability",
                        granularity="atomic",
                        source_claim_refs=("claim-a", "claim-b"),
                        triples=(
                            {
                                "subject": "Product",
                                "predicate": "has_capability",
                                "object": "refunds",
                                "qualifiers": [],
                            },
                        ),
                    ),
                ),
            ),
        ),
        created_at=_now(),
        updated_at=_now(),
    )


@dataclass(slots=True)
class FakeConnection:
    rows: dict[str, dict[str, object]] = field(default_factory=dict)

    async def execute(self, query: str, *args: object) -> str:
        del query
        workflow_run_id = str(args[0])
        self.rows[workflow_run_id] = {
            "workflow_run_id": workflow_run_id,
            "preview_payload": args[1],
            "claim_count": args[2],
            "group_count": args[3],
            "created_at": args[4],
            "updated_at": args[5],
        }
        return "INSERT 0 1"

    async def fetchrow(self, query: str, *args: object) -> object | None:
        del query
        return self.rows.get(str(args[0]))


@pytest.mark.asyncio
async def test_save_preview_upserts_and_loads_by_workflow_run_id() -> None:
    connection = FakeConnection()
    repository = PostgresDraftClaimClusterPreviewRepository(connection)

    first = await repository.save_preview(_preview())
    second = await repository.save_preview(_preview(claim="Updated refund claim."))

    assert first.created_preview is True
    assert second.updated_preview is True
    assert len(connection.rows) == 1

    loaded = await repository.load_preview(workflow_run_id="workflow-1")
    assert loaded is not None
    assert loaded.claim_count == 1
    assert loaded.groups[0].claims[0].claim == "Updated refund claim."
