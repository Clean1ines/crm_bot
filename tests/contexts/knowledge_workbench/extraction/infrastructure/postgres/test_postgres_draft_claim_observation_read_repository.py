from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from src.contexts.knowledge_workbench.extraction.infrastructure.postgres.postgres_draft_claim_observation_read_repository import (
    PostgresDraftClaimObservationReadRepository,
)


@dataclass(slots=True)
class FakeConnection:
    rows: list[Mapping[str, object]]
    calls: list[tuple[str, tuple[object, ...]]] = field(default_factory=list)

    async def fetch(self, query: str, *args: object) -> list[Mapping[str, object]]:
        self.calls.append((query, args))
        return self.rows


def _row(
    *,
    observation_ref: str = "draft-claim-observation:1",
    source_unit_ref: str = "source-unit:1",
    claim: str = "System turns documents into knowledge.",
    granularity: str = "atomic",
    possible_questions: tuple[str, ...] = ("What does the system do?",),
    exclusion_scope: str = "",
    evidence_block: str = "System turns documents into knowledge.",
    workflow_run_id: str | None = "workflow-1",
    stage_run_id: str | None = "claim_builder_section_extraction",
    work_item_id: str | None = "work-1",
    work_item_attempt_id: str | None = "work-1:attempt-1",
    llm_task_id: str | None = "work-1",
    llm_attempt_id: str | None = "work-1:attempt-1",
    prompt_id: str | None = "faq_claim_observations",
    prompt_version: str | None = "v1",
    claim_index: int | None = 0,
    created_at: datetime = datetime(2026, 6, 13, 12, 0, tzinfo=timezone.utc),
) -> Mapping[str, object]:
    return {
        "observation_ref": observation_ref,
        "source_unit_ref": source_unit_ref,
        "claim": claim,
        "granularity": granularity,
        "possible_questions": possible_questions,
        "exclusion_scope": exclusion_scope,
        "evidence_block": evidence_block,
        "workflow_run_id": workflow_run_id,
        "stage_run_id": stage_run_id,
        "work_item_id": work_item_id,
        "work_item_attempt_id": work_item_attempt_id,
        "llm_task_id": llm_task_id,
        "llm_attempt_id": llm_attempt_id,
        "prompt_id": prompt_id,
        "prompt_version": prompt_version,
        "claim_index": claim_index,
        "created_at": created_at,
        "source_unit_ordinal": 0,
    }


@pytest.mark.asyncio
async def test_list_by_source_document_ref_returns_claims_joined_through_source_units_document_ref() -> (
    None
):
    connection = FakeConnection(rows=[_row()])
    repository = PostgresDraftClaimObservationReadRepository(connection)

    result = await repository.list_by_source_document_ref(
        source_document_ref="source-document:project-1:abc",
        limit=50,
        offset=0,
    )

    assert len(result) == 1
    assert result[0].observation_ref == "draft-claim-observation:1"
    assert result[0].source_unit_ref == "source-unit:1"
    query, args = connection.calls[0]
    assert "JOIN source_units AS su" in query
    assert "su.document_ref = $1" in query
    assert args == ("source-document:project-1:abc", 50, 0)


@pytest.mark.asyncio
async def test_list_by_source_unit_ref_returns_only_claims_for_that_source_unit() -> (
    None
):
    connection = FakeConnection(rows=[_row(source_unit_ref="source-unit:2")])
    repository = PostgresDraftClaimObservationReadRepository(connection)

    result = await repository.list_by_source_unit_ref(
        source_unit_ref="source-unit:2",
        limit=25,
        offset=5,
    )

    assert len(result) == 1
    assert result[0].source_unit_ref == "source-unit:2"
    query, args = connection.calls[0]
    assert "dco.source_unit_ref = $1" in query
    assert args == ("source-unit:2", 25, 5)


@pytest.mark.asyncio
async def test_list_by_observation_refs_returns_claims_for_requested_refs() -> None:
    connection = FakeConnection(
        rows=[
            _row(observation_ref="claim-b"),
            _row(observation_ref="claim-a"),
        ],
    )

    result = await PostgresDraftClaimObservationReadRepository(
        connection,
    ).list_by_observation_refs(
        observation_refs=("claim-a", "claim-b"),
    )

    assert tuple(item.observation_ref for item in result) == ("claim-a", "claim-b")
    query, args = connection.calls[0]
    assert "dco.observation_ref = ANY($1::text[])" in query
    assert args == (["claim-a", "claim-b"],)


@pytest.mark.asyncio
async def test_possible_questions_are_returned_ordered_by_query_ordinal() -> None:
    connection = FakeConnection(
        rows=[
            _row(
                possible_questions=(
                    "First question?",
                    "Second question?",
                ),
            ),
        ],
    )

    result = await PostgresDraftClaimObservationReadRepository(
        connection,
    ).list_by_source_unit_ref(
        source_unit_ref="source-unit:1",
        limit=50,
        offset=0,
    )

    assert result[0].possible_questions == (
        "First question?",
        "Second question?",
    )
    assert "array_agg(dpq.question ORDER BY dpq.ordinal)" in connection.calls[0][0]


@pytest.mark.asyncio
async def test_provenance_fields_are_returned_when_present() -> None:
    result = await PostgresDraftClaimObservationReadRepository(
        FakeConnection(rows=[_row()]),
    ).list_by_source_unit_ref(
        source_unit_ref="source-unit:1",
        limit=50,
        offset=0,
    )

    item = result[0]
    assert item.workflow_run_id == "workflow-1"
    assert item.stage_run_id == "claim_builder_section_extraction"
    assert item.work_item_id == "work-1"
    assert item.work_item_attempt_id == "work-1:attempt-1"
    assert item.llm_task_id == "work-1"
    assert item.llm_attempt_id == "work-1:attempt-1"
    assert item.prompt_id == "faq_claim_observations"
    assert item.prompt_version == "v1"
    assert item.claim_index == 0


@pytest.mark.asyncio
async def test_missing_provenance_does_not_drop_claim() -> None:
    result = await PostgresDraftClaimObservationReadRepository(
        FakeConnection(
            rows=[
                _row(
                    workflow_run_id=None,
                    stage_run_id=None,
                    work_item_id=None,
                    work_item_attempt_id=None,
                    llm_task_id=None,
                    llm_attempt_id=None,
                    prompt_id=None,
                    prompt_version=None,
                    claim_index=None,
                )
            ],
        ),
    ).list_by_source_unit_ref(
        source_unit_ref="source-unit:1",
        limit=50,
        offset=0,
    )

    assert len(result) == 1
    assert result[0].workflow_run_id is None
    assert result[0].prompt_id is None


@pytest.mark.asyncio
async def test_limit_must_be_positive() -> None:
    with pytest.raises(ValueError, match="limit"):
        await PostgresDraftClaimObservationReadRepository(
            FakeConnection(rows=[]),
        ).list_by_source_document_ref(
            source_document_ref="source-document:1",
            limit=0,
            offset=0,
        )


@pytest.mark.asyncio
async def test_offset_must_be_non_negative() -> None:
    with pytest.raises(ValueError, match="offset"):
        await PostgresDraftClaimObservationReadRepository(
            FakeConnection(rows=[]),
        ).list_by_source_unit_ref(
            source_unit_ref="source-unit:1",
            limit=50,
            offset=-1,
        )


@pytest.mark.asyncio
async def test_document_level_ordering_is_by_source_unit_ordinal_then_claim_index() -> (
    None
):
    connection = FakeConnection(rows=[_row()])
    await PostgresDraftClaimObservationReadRepository(
        connection,
    ).list_by_source_document_ref(
        source_document_ref="source-document:1",
        limit=50,
        offset=0,
    )

    query = connection.calls[0][0]
    assert (
        "ORDER BY\n"
        "    su.ordinal ASC,\n"
        "    p.claim_index ASC NULLS LAST,\n"
        "    dco.created_at ASC,\n"
        "    dco.observation_ref ASC"
    ) in query
