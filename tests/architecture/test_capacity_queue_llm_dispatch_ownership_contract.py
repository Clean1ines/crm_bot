from __future__ import annotations

import inspect


def test_capacity_queue_runtime_core_enabled_but_llm_dispatch_cutover_disabled() -> (
    None
):
    from src.contexts.knowledge_workbench.application.sagas.llm_dispatch_ownership import (
        CAPACITY_QUEUE_RUNTIME_CORE_ENABLED,
        CAPACITY_QUEUE_OWNS_LLM_DISPATCH,
        CLAIM_BUILDER_CAPACITY_DRAIN_BRIDGE_ENABLED,
        DRAFT_CLAIM_COMPACTION_CAPACITY_DRAIN_BRIDGE_ENABLED,
    )

    assert CAPACITY_QUEUE_RUNTIME_CORE_ENABLED is True
    assert CLAIM_BUILDER_CAPACITY_DRAIN_BRIDGE_ENABLED is True
    assert DRAFT_CLAIM_COMPACTION_CAPACITY_DRAIN_BRIDGE_ENABLED is False
    assert CAPACITY_QUEUE_OWNS_LLM_DISPATCH is False


def test_no_prepare_guards_are_phase_specific() -> None:
    from src.contexts.knowledge_workbench.application.sagas import (
        handle_reconcile_claim_builder_progress_command as claim_builder_reconcile,
        handle_reconcile_draft_claim_compaction_progress_command as compaction_reconcile,
        handle_schedule_claim_builder_section_work_command as claim_builder_schedule,
    )

    claim_builder_schedule_source = inspect.getsource(
        claim_builder_schedule.HandleScheduleClaimBuilderSectionWorkCommandHandler.execute
    )
    claim_builder_reconcile_source = inspect.getsource(
        claim_builder_reconcile._next_command
    )
    compaction_reconcile_source = inspect.getsource(compaction_reconcile._next_command)

    assert "CLAIM_BUILDER_CAPACITY_DRAIN_BRIDGE_ENABLED" in (
        claim_builder_schedule_source
    )
    assert "CLAIM_BUILDER_CAPACITY_DRAIN_BRIDGE_ENABLED" in (
        claim_builder_reconcile_source
    )
    assert "DRAFT_CLAIM_COMPACTION_CAPACITY_DRAIN_BRIDGE_ENABLED" in (
        compaction_reconcile_source
    )
