from src.contexts.knowledge_workbench.observability.application.read_models.workbench_document_workflow_live_state import (
    WorkbenchCurationAvailabilityView,
)
from src.interfaces.composition.faq_workbench_workflow_live_state import _actions


def test_pending_daily_capacity_choice_exposes_confirmation_action() -> None:
    actions = _actions(
        workflow_status="RUNNING",
        curation=WorkbenchCurationAvailabilityView(
            available=False,
            reason_code="preview_not_ready",
            workflow_run_id="workflow-1",
            workspace_ref=None,
            workspace_status=None,
            item_count=0,
            excluded_item_count=0,
        ),
        degraded_fallback_confirmation_pending=True,
    )

    confirmation = next(
        action for action in actions if action.action_id == "confirm_degraded_fallback"
    )
    assert confirmation.visible is True
    assert confirmation.enabled is True
