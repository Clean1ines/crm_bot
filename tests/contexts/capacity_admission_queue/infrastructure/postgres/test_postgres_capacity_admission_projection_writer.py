from dataclasses import dataclass

import pytest
from typing import cast

from src.contexts.capacity_admission_queue.application.build_capacity_admission_projection_candidates import (
    CapacityAdmissionWorkItemProjectionCandidate,
)
from src.contexts.capacity_admission_queue.infrastructure.postgres.postgres_capacity_admission_projection_writer import (
    PostgresCapacityAdmissionProjectionWriter,
)
from src.contexts.execution_runtime.domain.value_objects.work_item_status import (
    WorkItemStatus,
)


@dataclass(frozen=True, slots=True)
class ExecuteCall:
    query: str
    args: tuple[object, ...]


class FakeConnection:
    def __init__(self) -> None:
        self.execute_calls: list[ExecuteCall] = []

    async def execute(self, query: str, *args: object) -> str:
        self.execute_calls.append(ExecuteCall(query=query, args=args))
        return "OK"


def _candidate(
    *,
    work_item_id: str = "work-item-1",
    work_kind: str = "knowledge.claim_builder",
    provider: str = "groq",
    account_ref: str | None = "groq-account-1",
    model_ref: str = "llama-3.3-70b-versatile",
    reserved_total_tokens: int = 130,
) -> CapacityAdmissionWorkItemProjectionCandidate:
    return CapacityAdmissionWorkItemProjectionCandidate(
        work_item_id=work_item_id,
        work_kind=work_kind,
        workflow_run_id="11111111-1111-1111-1111-111111111111",
        project_id="22222222-2222-2222-2222-222222222222",
        provider=provider,
        account_ref=account_ref,
        model_ref=model_ref,
        status=WorkItemStatus.READY,
        retry_plan=None,
        estimated_input_tokens=100,
        estimated_output_tokens=30,
        effective_output_cap_tokens=30,
        reserved_total_tokens=reserved_total_tokens,
        source_ref={
            "workflow_run_id": "11111111-1111-1111-1111-111111111111",
            "source_document_ref": "source-document-1",
            "source_unit_ref": "source-unit-1",
        },
    )


@pytest.mark.asyncio
async def test_empty_candidates_do_not_write_sql() -> None:
    connection = FakeConnection()

    result = await PostgresCapacityAdmissionProjectionWriter(
        connection
    ).persist_projection_candidates(())

    assert result.persisted_count == 0
    assert connection.execute_calls == []


@pytest.mark.asyncio
async def test_persists_projection_dirty_lane_and_due_work_event() -> None:
    connection = FakeConnection()

    result = await PostgresCapacityAdmissionProjectionWriter(
        connection
    ).persist_projection_candidates((_candidate(),))

    assert result.persisted_count == 1
    assert len(connection.execute_calls) == 3

    projection_call = connection.execute_calls[0]
    dirty_call = connection.execute_calls[1]
    event_call = connection.execute_calls[2]

    assert "INSERT INTO capacity_admission_work_items" in projection_call.query
    assert "ON CONFLICT (work_item_id) DO UPDATE SET" in projection_call.query
    assert projection_call.args[0] == "work-item-1"
    assert projection_call.args[1] == "knowledge.claim_builder"
    assert projection_call.args[4] == "groq"
    assert projection_call.args[5] == "groq-account-1"
    assert projection_call.args[6] == "llama-3.3-70b-versatile"
    assert projection_call.args[7] == WorkItemStatus.READY.value
    assert projection_call.args[9] == 100
    assert projection_call.args[10] == 30
    assert projection_call.args[11] == 30
    assert projection_call.args[12] == 130
    projection_source_ref_json = _string_arg(projection_call.args[13])
    assert '"source_document_ref":"source-document-1"' in projection_source_ref_json

    assert "INSERT INTO capacity_admission_lane_dirty_flags" in dirty_call.query
    assert "ON CONFLICT (lane_id) DO UPDATE SET" in dirty_call.query
    assert dirty_call.args[0] == (
        "knowledge.claim_builder:groq:groq-account-1:llama-3.3-70b-versatile"
    )
    assert dirty_call.args[5] == "scheduled_projection_upserted"

    assert "INSERT INTO capacity_admission_lane_events" in event_call.query
    assert event_call.args[2] == "DueWorkQueueChanged"
    assert event_call.args[7] == "work-item-1"
    assert event_call.args[8] == "scheduled_projection_upserted"
    event_payload_json = _string_arg(event_call.args[9])
    assert '"reserved_total_tokens":130' in event_payload_json


@pytest.mark.asyncio
async def test_coalesces_dirty_lane_and_event_once_per_lane_per_batch() -> None:
    connection = FakeConnection()

    result = await PostgresCapacityAdmissionProjectionWriter(
        connection
    ).persist_projection_candidates(
        (
            _candidate(work_item_id="work-item-1"),
            _candidate(work_item_id="work-item-2"),
        )
    )

    assert result.persisted_count == 2
    assert len(connection.execute_calls) == 4

    projection_calls = [
        call
        for call in connection.execute_calls
        if "INSERT INTO capacity_admission_work_items" in call.query
    ]
    dirty_calls = [
        call
        for call in connection.execute_calls
        if "INSERT INTO capacity_admission_lane_dirty_flags" in call.query
    ]
    event_calls = [
        call
        for call in connection.execute_calls
        if "INSERT INTO capacity_admission_lane_events" in call.query
    ]

    assert len(projection_calls) == 2
    assert len(dirty_calls) == 1
    assert len(event_calls) == 1


@pytest.mark.asyncio
async def test_different_lanes_get_separate_dirty_flags_and_events() -> None:
    connection = FakeConnection()

    result = await PostgresCapacityAdmissionProjectionWriter(
        connection
    ).persist_projection_candidates(
        (
            _candidate(work_item_id="work-item-1", model_ref="model-a"),
            _candidate(work_item_id="work-item-2", model_ref="model-b"),
        )
    )

    assert result.persisted_count == 2
    assert len(connection.execute_calls) == 6

    dirty_lane_ids = [
        call.args[0]
        for call in connection.execute_calls
        if "INSERT INTO capacity_admission_lane_dirty_flags" in call.query
    ]

    assert dirty_lane_ids == [
        "knowledge.claim_builder:groq:groq-account-1:model-a",
        "knowledge.claim_builder:groq:groq-account-1:model-b",
    ]


@pytest.mark.asyncio
async def test_lane_id_uses_dash_when_account_ref_is_absent() -> None:
    connection = FakeConnection()

    await PostgresCapacityAdmissionProjectionWriter(
        connection
    ).persist_projection_candidates((_candidate(account_ref=None),))

    dirty_call = next(
        call
        for call in connection.execute_calls
        if "INSERT INTO capacity_admission_lane_dirty_flags" in call.query
    )

    assert dirty_call.args[0] == (
        "knowledge.claim_builder:groq:-:llama-3.3-70b-versatile"
    )


@pytest.mark.asyncio
async def test_rejects_non_tuple_candidates_batch() -> None:
    connection = FakeConnection()
    invalid_batch = _invalid_non_tuple_candidate_batch()

    with pytest.raises(TypeError, match="candidates must be tuple"):
        await PostgresCapacityAdmissionProjectionWriter(
            connection
        ).persist_projection_candidates(invalid_batch)


@pytest.mark.asyncio
async def test_rejects_non_projection_candidate_item() -> None:
    connection = FakeConnection()
    invalid_candidates = _invalid_projection_candidate_tuple()

    with pytest.raises(
        TypeError,
        match="CapacityAdmissionWorkItemProjectionCandidate",
    ):
        await PostgresCapacityAdmissionProjectionWriter(
            connection
        ).persist_projection_candidates(invalid_candidates)


def _string_arg(value: object) -> str:
    if not isinstance(value, str):
        raise AssertionError("expected string argument")
    return value


def _invalid_non_tuple_candidate_batch() -> tuple[
    CapacityAdmissionWorkItemProjectionCandidate, ...
]:
    return cast(tuple[CapacityAdmissionWorkItemProjectionCandidate, ...], [])


def _invalid_projection_candidate_tuple() -> tuple[
    CapacityAdmissionWorkItemProjectionCandidate, ...
]:
    return cast(
        tuple[CapacityAdmissionWorkItemProjectionCandidate, ...],
        ("not-a-candidate",),
    )
