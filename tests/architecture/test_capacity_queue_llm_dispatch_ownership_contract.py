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


def test_trigger_claim_builder_capacity_drain_command_type_exists() -> None:
    from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
        KnowledgeExtractionCanonicalCommandType,
    )

    assert (
        KnowledgeExtractionCanonicalCommandType.TRIGGER_CLAIM_BUILDER_CAPACITY_DRAIN.value
        == "TriggerClaimBuilderCapacityDrain"
    )


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
    claim_builder_reconcile_trigger_source = inspect.getsource(
        claim_builder_reconcile._capacity_drain_trigger_command
    )
    compaction_reconcile_source = inspect.getsource(compaction_reconcile._next_command)

    assert "current_llm_dispatch_ownership_policy" in claim_builder_schedule_source
    assert "claim_builder_capacity_queue_owns_dispatch" in (
        claim_builder_schedule_source
    )
    assert "current_llm_dispatch_ownership_policy" in claim_builder_reconcile_source
    assert "claim_builder_capacity_queue_owns_dispatch" in (
        claim_builder_reconcile_source
    )
    assert "draft_claim_compaction_capacity_queue_owns_dispatch" in (
        compaction_reconcile_source
    )
    assert "_capacity_drain_trigger_command" in claim_builder_schedule_source
    assert "_capacity_drain_trigger_command" in claim_builder_reconcile_source
    assert "build_claim_builder_capacity_drain_trigger_command" in (
        claim_builder_reconcile_trigger_source
    )


def test_llm_dispatch_ownership_policy_exists() -> None:
    from src.contexts.knowledge_workbench.application.sagas.llm_dispatch_ownership_policy import (
        LlmDispatchOwnershipPolicy,
        current_llm_dispatch_ownership_policy,
    )

    policy = current_llm_dispatch_ownership_policy()

    assert isinstance(policy, LlmDispatchOwnershipPolicy)
    assert policy.capacity_queue_owns_llm_dispatch is False
