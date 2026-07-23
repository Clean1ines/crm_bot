from pathlib import Path
import ast
from decimal import Decimal, ROUND_CEILING

import pytest

from src.contexts.execution_runtime.application.use_cases.ensure_work_items_scheduled import (
    WorkItemSchedulePlan,
    work_item_schedule_payload_hash,
)
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.knowledge_workbench.application.sagas.map_claim_builder_section_plans_to_execution_schedule import (
    CLAIM_BUILDER_DEFAULT_PROMPT_TOKENS,
    CLAIM_BUILDER_INPUT_SAFETY_GAP_TOKENS,
    MapClaimBuilderSectionPlansToExecutionSchedule,
    MapClaimBuilderSectionPlansToExecutionScheduleCommand,
    MapClaimBuilderSectionPlansToExecutionScheduleResult,
    _estimate_artifact_tokens_from_chars,
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
    user_content = _single_user_content(provider_messages)
    assert "source_unit_ref:" not in user_content
    assert plan.source_unit_ref.value not in user_content
    assert "heading_path:" in user_content
    assert plan.source_unit_text in user_content

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
    assert capacity_estimate["budget_contract_version"] == "v3"
    assert capacity_estimate["phase"] == "claim_builder_section_extraction"
    assert capacity_estimate["model_ref"] == "qwen/qwen3.6-27b"
    assert capacity_estimate["model_tpm_limit"] == 8_000
    assert capacity_estimate["model_char_to_token_multiplier"] == "2.8"
    assert capacity_estimate["prompt_tokens"] == CLAIM_BUILDER_DEFAULT_PROMPT_TOKENS
    assert capacity_estimate["input_tokens"] == (
        CLAIM_BUILDER_DEFAULT_PROMPT_TOKENS + capacity_estimate["artifact_tokens"]
    )
    assert (
        capacity_estimate["planned_output_tokens"]
        == (capacity_estimate["artifact_tokens"])
    )
    assert capacity_estimate["required_window_tokens"] == (
        capacity_estimate["input_tokens"]
        + capacity_estimate["planned_output_tokens"]
        + capacity_estimate["safety_gap_tokens"]
    )
    forbidden_keys = (
        "estimated_" + "input_tokens",
        "reserved_" + "output_tokens",
        "estimated_" + "total_tokens",
    )
    assert not set(forbidden_keys) & set(capacity_estimate)


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
    assert capacity_estimate["prompt_tokens"] == 4200
    assert capacity_estimate["input_tokens"] == (
        4200 + capacity_estimate["artifact_tokens"]
    )
    assert capacity_estimate["required_window_tokens"] == (
        capacity_estimate["input_tokens"]
        + capacity_estimate["planned_output_tokens"]
        + capacity_estimate["safety_gap_tokens"]
    )
    assert capacity_estimate["estimator"].startswith("measured_prompt_4200_")


def test_qwen36_artifact_tokens_use_ceiling_char_multiplier() -> None:
    assert (
        _estimate_artifact_tokens_from_chars(
            char_count=1031,
            model_char_to_token_multiplier=Decimal("2.8"),
        )
        == 369
    )


def test_default_claim_builder_schedule_budget_matches_calibrated_qwen36(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CLAIM_BUILDER_PROMPT_TOKENS", raising=False)
    plan = _plan(
        source_unit_ref="source-unit:project-1:calibration:0",
        heading_path=("Возвраты", "Сроки"),
        source_unit_text="Возврат выполняется в течение 14 дней.",
    )

    schedule = (
        MapClaimBuilderSectionPlansToExecutionSchedule()
        .execute(_command((plan,)))
        .schedule_plans[0]
    )

    user_content = _single_user_content(schedule.payload["provider_messages"])
    expected_artifact_tokens = _ceil_div_decimal(
        len(user_content),
        Decimal("2.8"),
    )
    capacity = schedule.payload["llm_capacity_estimate"]
    assert isinstance(capacity, dict)
    assert schedule.payload["source_unit_ref"] == plan.source_unit_ref.value
    assert schedule.payload["claim_builder_provenance"]["source_unit_ref"] == (
        plan.source_unit_ref.value
    )
    assert "source_unit_ref:" not in user_content
    assert plan.source_unit_ref.value not in user_content
    assert "heading_path:" in user_content
    assert plan.source_unit_text in user_content
    assert capacity["budget_contract_version"] == "v3"
    assert capacity["model_ref"] == "qwen/qwen3.6-27b"
    assert capacity["prompt_tokens"] == 3_008
    assert capacity["artifact_tokens"] == expected_artifact_tokens
    assert capacity["input_tokens"] == 3_008 + expected_artifact_tokens
    assert capacity["planned_output_tokens"] == capacity["artifact_tokens"]
    assert capacity["safety_gap_tokens"] == CLAIM_BUILDER_INPUT_SAFETY_GAP_TOKENS
    assert capacity["required_window_tokens"] == (
        capacity["input_tokens"]
        + capacity["planned_output_tokens"]
        + CLAIM_BUILDER_INPUT_SAFETY_GAP_TOKENS
    )


def _single_user_content(provider_messages: object) -> str:
    assert isinstance(provider_messages, tuple)
    user_contents = tuple(
        message["content"]
        for message in provider_messages
        if isinstance(message, dict) and message.get("role") == "user"
    )
    assert len(user_contents) == 1
    content = user_contents[0]
    assert isinstance(content, str)
    return content


def _ceil_div_decimal(value: int, divisor: Decimal) -> int:
    return int(
        (Decimal(value) / divisor).to_integral_value(rounding=ROUND_CEILING),
    )


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
    )
    forbidden_markers = (
        "EnsureWorkItemsScheduled",
        "WorkItemSchedulingRepositoryPort",
        "capacity_runtime",
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
    )

    for marker in required_markers:
        assert marker in source

    for marker in forbidden_markers:
        assert marker not in source

    allowed_llm_runtime_imports = {
        "src.contexts.llm_runtime.application.capacity.llm_capacity_estimate_payload",
    }
    llm_runtime_imports = {
        module_name
        for module_name in _imported_module_names(source)
        if module_name.startswith("src.contexts.llm_runtime.")
    }
    assert llm_runtime_imports <= allowed_llm_runtime_imports


def _imported_module_names(source: str) -> set[str]:
    tree = ast.parse(source)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            names.add(node.module)
        elif isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
    return names
