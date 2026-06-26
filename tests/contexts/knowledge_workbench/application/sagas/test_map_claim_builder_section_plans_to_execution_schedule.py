from pathlib import Path

import pytest

from src.contexts.execution_runtime.application.use_cases.ensure_work_items_scheduled import (
    WorkItemSchedulePlan,
    work_item_schedule_payload_hash,
)
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.knowledge_workbench.application.sagas.map_claim_builder_section_plans_to_execution_schedule import (
    MapClaimBuilderSectionPlansToExecutionSchedule,
    MapClaimBuilderSectionPlansToExecutionScheduleCommand,
    MapClaimBuilderSectionPlansToExecutionScheduleResult,
)
from src.contexts.knowledge_workbench.application.sagas.plan_claim_builder_section_work import (
    ClaimBuilderSectionWorkPlan,
)
from src.contexts.knowledge_workbench.extraction.application.policies.claim_builder_section_extraction_prompt_contract import (
    BuildClaimBuilderSectionExtractionPrompt,
    ClaimBuilderSectionExtractionPromptInput,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_document_ref import (
    SourceDocumentRef,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_ref import (
    SourceUnitRef,
)


def _plan(
    *,
    work_item_id: str = "knowledge-workbench:claim-builder:section-extraction:run-1:unit-1",
    workflow_run_id: str = "run-1",
    source_document_ref: str = "source-document:project-1:abc",
    source_unit_ref: str = "source-unit:project-1:abc:0",
    source_unit_ordinal: int = 0,
    source_unit_text: str = "# Unit 0\n\nBody",
    heading_path: tuple[str, ...] = ("Unit 0",),
) -> ClaimBuilderSectionWorkPlan:
    return ClaimBuilderSectionWorkPlan(
        workflow_run_id=workflow_run_id,
        source_document_ref=SourceDocumentRef(source_document_ref),
        source_unit_ref=SourceUnitRef(source_unit_ref),
        source_unit_ordinal=source_unit_ordinal,
        source_unit_text=source_unit_text,
        heading_path=heading_path,
        work_item_id=work_item_id,
        work_kind=WorkKind("knowledge_workbench.claim_builder.section_extraction"),
        idempotency_key=work_item_id,
    )


def _command(
    plans: tuple[ClaimBuilderSectionWorkPlan, ...],
) -> MapClaimBuilderSectionPlansToExecutionScheduleCommand:
    return MapClaimBuilderSectionPlansToExecutionScheduleCommand(plans=plans)


def test_maps_one_workbench_plan_to_execution_schedule_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CLAIM_BUILDER_PROMPT_TOKENS", raising=False)
    plan = _plan()

    result = MapClaimBuilderSectionPlansToExecutionSchedule().execute(
        _command((plan,)),
    )

    assert isinstance(result, MapClaimBuilderSectionPlansToExecutionScheduleResult)
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
    assert schedule.payload["phase"] == "claim_builder_section_extraction"
    prompt_contract = BuildClaimBuilderSectionExtractionPrompt().execute(
        ClaimBuilderSectionExtractionPromptInput(
            source_unit_ref=plan.source_unit_ref.value,
            heading_path=plan.heading_path,
            source_unit_text=plan.source_unit_text,
        ),
    )

    provider_messages = schedule.payload["provider_messages"]
    assert provider_messages == prompt_contract.provider_messages

    claim_builder_provenance = schedule.payload["claim_builder_provenance"]
    assert claim_builder_provenance == {
        "workflow_run_id": plan.workflow_run_id,
        "stage_run_id": "claim_builder_section_extraction",
        "source_unit_ref": plan.source_unit_ref.value,
        "work_item_id": plan.work_item_id,
        "prompt_id": prompt_contract.prompt_id,
        "prompt_version": prompt_contract.prompt_version,
    }


def test_repeated_mapping_is_deterministic() -> None:
    command = _command(
        (
            _plan(work_item_id="work-2", source_unit_ordinal=2),
            _plan(work_item_id="work-1", source_unit_ordinal=1),
        ),
    )
    use_case = MapClaimBuilderSectionPlansToExecutionSchedule()

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
    use_case = MapClaimBuilderSectionPlansToExecutionSchedule()

    first = use_case.execute(command).schedule_plans[0]
    second = use_case.execute(command).schedule_plans[0]

    assert work_item_schedule_payload_hash(
        first.payload,
    ) == work_item_schedule_payload_hash(second.payload)


def test_payload_contains_claim_builder_dispatch_seed_without_attempt_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CLAIM_BUILDER_PROMPT_TOKENS", raising=False)
    plan = _plan()
    schedule = (
        MapClaimBuilderSectionPlansToExecutionSchedule()
        .execute(
            _command((plan,)),
        )
        .schedule_plans[0]
    )

    assert set(schedule.payload) == {
        "workflow_run_id",
        "source_document_ref",
        "source_unit_ref",
        "source_unit_ordinal",
        "phase",
        "provider_messages",
        "claim_builder_provenance",
        "llm_capacity_estimate",
    }
    assert "work_item_attempt_id" not in schedule.payload
    assert "llm_task_id" not in schedule.payload
    assert "llm_attempt_id" not in schedule.payload
    assert "raw_text" not in schedule.payload
    assert "text_preview" not in schedule.payload
    assert "prompt_text" not in schedule.payload

    provenance = schedule.payload["claim_builder_provenance"]
    assert provenance == {
        "workflow_run_id": plan.workflow_run_id,
        "stage_run_id": "claim_builder_section_extraction",
        "source_unit_ref": plan.source_unit_ref.value,
        "work_item_id": plan.work_item_id,
        "prompt_id": "faq_claim_observations",
        "prompt_version": "v1",
    }

    capacity_estimate = schedule.payload["llm_capacity_estimate"]
    assert isinstance(capacity_estimate, dict)
    assert capacity_estimate["budget_contract_version"] == "v1"
    assert capacity_estimate["provider"] == "groq"
    assert capacity_estimate["model_ref"] == "qwen/qwen3-32b"
    assert capacity_estimate["model_tpm_limit"] == 6000
    assert capacity_estimate["model_char_to_token_multiplier"] == "3.3"
    assert capacity_estimate["prompt_id"] == "faq_claim_observations"
    assert capacity_estimate["prompt_version"] == "v1"
    assert capacity_estimate["phase"] == "claim_builder"
    assert capacity_estimate["operation"] == "section_claim_extraction"
    assert capacity_estimate["input_artifact_kind"] == "source_unit"
    assert capacity_estimate["output_artifact_kind"] == "draft_claims"
    assert capacity_estimate["request_safety_gap_tokens"] == 300
    assert capacity_estimate["output_safety_gap_tokens"] == 300
    assert capacity_estimate["provider_default_completion_tokens"] == 2048

    assert capacity_estimate["prompt_message_tokens"] == (1953,)
    assert capacity_estimate["prompt_tokens"] == 1953
    assert (
        capacity_estimate["source_unit_token_count"]
        == (capacity_estimate["artifact_token_estimate"])
    )
    assert (
        capacity_estimate["batch_input_estimated_tokens"]
        == (capacity_estimate["source_unit_token_count"])
    )
    assert capacity_estimate["max_artifact_input_tokens"] == 1873
    assert capacity_estimate["batch_input_max_tokens"] == 1873
    assert capacity_estimate["planned_output_reserve_tokens"] == 1874
    assert capacity_estimate["estimated_output_tokens"] == 1874

    assert capacity_estimate["estimated_input_tokens"] == (
        1953 + capacity_estimate["source_unit_token_count"]
    )
    assert (
        capacity_estimate["request_input_estimated_tokens"]
        == (capacity_estimate["estimated_input_tokens"])
    )
    assert capacity_estimate["remaining_after_actual_input_tokens"] == (
        6000 - capacity_estimate["estimated_input_tokens"] - 300
    )
    assert (
        capacity_estimate["request_output_cap_tokens"]
        == (capacity_estimate["remaining_after_actual_input_tokens"])
    )
    assert (
        capacity_estimate["effective_output_cap_tokens"]
        == (capacity_estimate["request_output_cap_tokens"])
    )
    assert capacity_estimate["reserved_total_tokens"] == (
        capacity_estimate["estimated_input_tokens"]
        + capacity_estimate["effective_output_cap_tokens"]
    )
    assert "reserved_output_tokens" not in capacity_estimate
    assert capacity_estimate["estimated_total_tokens"] == (
        capacity_estimate["estimated_input_tokens"]
        + capacity_estimate["planned_output_reserve_tokens"]
    )
    assert (
        capacity_estimate["request_total_estimated_tokens"]
        == (capacity_estimate["estimated_total_tokens"])
    )


def test_prompt_token_count_can_be_overridden_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLAIM_BUILDER_PROMPT_TOKENS", "4200")
    plan = _plan()

    schedule = (
        MapClaimBuilderSectionPlansToExecutionSchedule()
        .execute(
            _command((plan,)),
        )
        .schedule_plans[0]
    )

    capacity_estimate = schedule.payload["llm_capacity_estimate"]
    assert capacity_estimate["prompt_message_tokens"] == (4200,)
    assert capacity_estimate["prompt_tokens"] == 4200
    assert capacity_estimate["max_artifact_input_tokens"] == 750
    assert capacity_estimate["planned_output_reserve_tokens"] == 750
    assert capacity_estimate["estimated_output_tokens"] == 750
    assert capacity_estimate["estimated_input_tokens"] == (
        4200 + capacity_estimate["source_unit_token_count"]
    )
    assert capacity_estimate["remaining_after_actual_input_tokens"] == (
        6000 - capacity_estimate["estimated_input_tokens"] - 300
    )
    assert "request_output_cap_tokens" not in capacity_estimate
    assert capacity_estimate["effective_output_cap_tokens"] == 750
    assert capacity_estimate["reserved_total_tokens"] == (
        capacity_estimate["estimated_input_tokens"] + 750
    )
    assert capacity_estimate["estimated_total_tokens"] == (
        capacity_estimate["estimated_input_tokens"] + 750
    )
    assert capacity_estimate["estimator"].startswith("measured_prompt_4200_")


def test_map_claim_builder_section_plans_to_execution_schedule_source_guard() -> None:
    source = Path(
        "src/contexts/knowledge_workbench/application/sagas/"
        "map_claim_builder_section_plans_to_execution_schedule.py",
    ).read_text(encoding="utf-8")

    required_markers = (
        "MapClaimBuilderSectionPlansToExecutionSchedule",
        "MapClaimBuilderSectionPlansToExecutionScheduleCommand",
        "MapClaimBuilderSectionPlansToExecutionScheduleResult",
        "WorkItemSchedulePlan",
        "ClaimBuilderSectionWorkPlan",
        "claim_builder_section_extraction",
        "source_document_ref",
        "source_unit_ref",
        "source_unit_ordinal",
        "provider_messages",
        "claim_builder_provenance",
        "BuildClaimBuilderSectionExtractionPrompt",
        "ClaimBuilderSectionExtractionPromptInput",
        "claim_builder_phase_token_budget_policy",
    )
    forbidden_markers = (
        "CLAIM_BUILDER_ROUGH_TOKEN_ESTIMATOR",
        "CLAIM_BUILDER_MODEL_TPM_TOKENS",
        "CLAIM_BUILDER_INPUT_SAFETY_GAP_TOKENS",
        "EnsureWorkItemsScheduled",
        "WorkItemSchedulingRepositoryPort",
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
        "Extract draft claim observations as strict JSON",
        "Use prompt_id faq_claim_observations",
        'prompt_version = "v1"',
        "Groq",
        "qwen",
    )

    for marker in required_markers:
        assert marker in source

    for marker in forbidden_markers:
        assert marker not in source
