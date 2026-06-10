from pathlib import Path

import pytest

from src.contexts.execution_runtime.application.use_cases.ensure_work_items_scheduled import (
    WorkItemSchedulePlan,
    work_item_schedule_payload_hash,
)
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.knowledge_workbench.application.sagas.map_draft_observation_plans_to_execution_schedule import (
    MapDraftObservationPlansToExecutionSchedule,
    MapDraftObservationPlansToExecutionScheduleCommand,
    MapDraftObservationPlansToExecutionScheduleResult,
)
from src.contexts.knowledge_workbench.application.sagas.plan_draft_observation_extraction_work import (
    DraftObservationExtractionWorkPlan,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_document_ref import (
    SourceDocumentRef,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_ref import (
    SourceUnitRef,
)


def _plan(
    *,
    work_item_id: str = "knowledge-workbench:draft-observation-extraction:run-1:unit-1",
    workflow_run_id: str = "run-1",
    source_document_ref: str = "source-document:project-1:abc",
    source_unit_ref: str = "source-unit:project-1:abc:0",
    source_unit_ordinal: int = 0,
) -> DraftObservationExtractionWorkPlan:
    return DraftObservationExtractionWorkPlan(
        workflow_run_id=workflow_run_id,
        source_document_ref=SourceDocumentRef(source_document_ref),
        source_unit_ref=SourceUnitRef(source_unit_ref),
        source_unit_ordinal=source_unit_ordinal,
        work_item_id=work_item_id,
        work_kind=WorkKind("knowledge_workbench.draft_observation_extraction"),
        idempotency_key=work_item_id,
    )


def _command(
    plans: tuple[DraftObservationExtractionWorkPlan, ...],
) -> MapDraftObservationPlansToExecutionScheduleCommand:
    return MapDraftObservationPlansToExecutionScheduleCommand(plans=plans)


def test_maps_one_workbench_plan_to_execution_schedule_plan() -> None:
    plan = _plan()

    result = MapDraftObservationPlansToExecutionSchedule().execute(
        _command((plan,)),
    )

    assert isinstance(result, MapDraftObservationPlansToExecutionScheduleResult)
    assert len(result.schedule_plans) == 1

    schedule = result.schedule_plans[0]
    assert isinstance(schedule, WorkItemSchedulePlan)
    assert schedule.work_item_id == plan.work_item_id
    assert schedule.work_kind == plan.work_kind
    assert schedule.idempotency_key == plan.idempotency_key
    assert schedule.payload["workflow_run_id"] == plan.workflow_run_id
    assert schedule.payload["source_document_ref"] == plan.source_document_ref.value
    assert schedule.payload["source_unit_ref"] == plan.source_unit_ref.value
    assert schedule.payload["source_unit_ordinal"] == plan.source_unit_ordinal
    assert schedule.payload["phase"] == "draft_observation_extraction"


def test_repeated_mapping_is_deterministic() -> None:
    command = _command(
        (
            _plan(work_item_id="work-2", source_unit_ordinal=2),
            _plan(work_item_id="work-1", source_unit_ordinal=1),
        ),
    )
    use_case = MapDraftObservationPlansToExecutionSchedule()

    first = use_case.execute(command)
    second = use_case.execute(command)

    assert first == second


def test_duplicate_work_item_id_is_rejected() -> None:
    with pytest.raises(ValueError, match="work_item_id must be unique"):
        _command(
            (
                _plan(work_item_id="duplicate", source_unit_ref="unit-1"),
                _plan(work_item_id="duplicate", source_unit_ref="unit-2"),
            ),
        )


def test_payload_hash_is_stable_through_execution_runtime_helper() -> None:
    command = _command((_plan(),))
    use_case = MapDraftObservationPlansToExecutionSchedule()

    first = use_case.execute(command).schedule_plans[0]
    second = use_case.execute(command).schedule_plans[0]

    assert work_item_schedule_payload_hash(
        first.payload,
    ) == work_item_schedule_payload_hash(second.payload)


def test_payload_is_stable_json_serializable_schedule_metadata_only() -> None:
    schedule = (
        MapDraftObservationPlansToExecutionSchedule()
        .execute(
            _command((_plan(),)),
        )
        .schedule_plans[0]
    )

    assert tuple(schedule.payload) == (
        "workflow_run_id",
        "source_document_ref",
        "source_unit_ref",
        "source_unit_ordinal",
        "phase",
    )
    assert "raw_text" not in schedule.payload
    assert "text_preview" not in schedule.payload
    assert "prompt_text" not in schedule.payload


def test_map_draft_observation_plans_to_execution_schedule_source_guard() -> None:
    source = Path(
        "src/contexts/knowledge_workbench/application/sagas/"
        "map_draft_observation_plans_to_execution_schedule.py",
    ).read_text(encoding="utf-8")

    required_markers = (
        "MapDraftObservationPlansToExecutionSchedule",
        "MapDraftObservationPlansToExecutionScheduleCommand",
        "MapDraftObservationPlansToExecutionScheduleResult",
        "WorkItemSchedulePlan",
        "DraftObservationExtractionWorkPlan",
        "draft_observation_extraction",
        "source_document_ref",
        "source_unit_ref",
        "source_unit_ordinal",
    )
    forbidden_markers = (
        "EnsureWorkItemsScheduled",
        "WorkItemSchedulingUnitOfWorkPort",
        "capacity_runtime",
        "llm_runtime",
        "artifact_runtime",
        "execution_runtime.infrastructure",
        "Postgres",
        "asyncpg",
        "queue",
        "worker",
        "lease",
        "raw_text",
        "text_preview",
        "prompt_text",
        "Groq",
        "qwen",
    )

    for marker in required_markers:
        assert marker in source

    for marker in forbidden_markers:
        assert marker not in source
