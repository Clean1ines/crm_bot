from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_route_activation_events_are_canonical_workflow_events() -> None:
    source = (
        ROOT
        / "src/contexts/knowledge_workbench/application/sagas/knowledge_extraction_workflow_definition.py"
    ).read_text(encoding="utf-8")

    for marker in (
        "ROUTE_ACTIVATION_CREATED",
        "ROUTE_ACTIVATION_CLOSED",
        "WORK_ITEM_REROUTE_REQUESTED",
        "WORK_ITEM_REROUTED",
        "CAPACITY_WINDOW_WAITING_DUE_WORK",
        "CAPACITY_WINDOW_ADMISSION_SKIPPED",
    ):
        assert marker in source


def test_route_activation_frontend_projector_is_plugged_into_root_projector() -> None:
    root_projector = (
        ROOT
        / "src/contexts/knowledge_workbench/observability/application/projectors/knowledge_extraction_frontend_workflow_event_projector.py"
    ).read_text(encoding="utf-8")
    route_projector = (
        ROOT
        / "src/contexts/knowledge_workbench/observability/application/projectors/route_activation_frontend_workflow_event_projector.py"
    ).read_text(encoding="utf-8")

    assert "RouteActivationFrontendWorkflowEventProjector" in root_projector
    assert "workflow_route_activation_created" in route_projector
    assert "workflow_work_item_reroute_requested" in route_projector


def test_phase_route_policy_vocabulary_separates_phase_routes_from_provider_catalog() -> (
    None
):
    source = (
        ROOT / "src/contexts/llm_runtime/domain/routing/phase_route_policy.py"
    ).read_text(encoding="utf-8")

    for marker in (
        "PhaseRouteKind",
        "PhaseRouteReason",
        "PhaseRouteActivationScope",
        "PhaseRoutePolicy",
        "MANUAL_FALLBACK",
        "SPECIAL",
        "EMPTY_CLAIMS_VALIDATION",
        "INPUT_TOO_LARGE",
    ):
        assert marker in source


def test_knowledge_extraction_phase_route_policies_are_workbench_specific() -> None:
    policy_source = (
        ROOT
        / "src/contexts/knowledge_workbench/application/routing/knowledge_extraction_phase_route_policies.py"
    ).read_text(encoding="utf-8")
    generic_source = (
        ROOT / "src/contexts/llm_runtime/domain/routing/phase_route_policy.py"
    ).read_text(encoding="utf-8")

    assert "claim_builder_groq_free_phase_route_policy" in policy_source
    assert "draft_claim_compaction_groq_free_phase_route_policy" in policy_source
    assert "knowledge_workbench.claim_builder.section_extraction" not in generic_source
    assert "knowledge_workbench.draft_claim_compaction" not in generic_source


def test_phase_route_policies_keep_gpt_oss_out_of_claim_builder_daily_fallbacks() -> (
    None
):
    policy_source = (
        ROOT
        / "src/contexts/knowledge_workbench/application/routing/knowledge_extraction_phase_route_policies.py"
    ).read_text(encoding="utf-8")

    assert "CLAIM_BUILDER_SPECIAL_EMPTY_CLAIMS_GPT_OSS_ROUTE_REF" in policy_source
    assert "CLAIM_BUILDER_SPECIAL_INPUT_TOO_LARGE_GPT_OSS_ROUTE_REF" in policy_source
    assert "CLAIM_BUILDER_SPECIAL_OUTPUT_TOO_LARGE_GPT_OSS_ROUTE_REF" in policy_source
    assert "CLAIM_BUILDER_SPECIAL_TRUNCATED_JSON_GPT_OSS_ROUTE_REF" in policy_source
    assert "CLAIM_BUILDER_AUTO_LLAMA_VERSATILE_ROUTE_REF" in policy_source
    assert "CLAIM_BUILDER_AUTO_LLAMA_SCOUT_ROUTE_REF" in policy_source


def test_provider_capacity_window_vocabulary_separates_scope_from_slot() -> None:
    source = (
        ROOT / "src/contexts/llm_runtime/domain/routing/provider_capacity_windows.py"
    ).read_text(encoding="utf-8")

    for marker in (
        "CapacityScopeKey",
        "CapacityExecutionSlotKey",
        "CapacityExecutionWindow",
        "ProviderCapacityProfile",
        "ProviderParallelismPolicy",
        "ProviderCapacityExecutionWindowExpander",
    ):
        assert marker in source

    assert "capacity_scope_key" in source
    assert "execution_slot_key" in source
    assert "slots_per_account_model_route" in source
