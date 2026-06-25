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
