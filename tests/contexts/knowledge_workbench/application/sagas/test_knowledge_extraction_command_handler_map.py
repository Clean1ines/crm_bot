from __future__ import annotations

from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_command_handler_map import (
    IMPLEMENTED_KNOWLEDGE_EXTRACTION_COMMAND_HANDLERS,
    implemented_handler_name_for,
    is_command_implemented,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalCommandType,
    command_types_used_by_operations,
)


def test_implemented_handlers_are_subset_of_canonical_workflow_command_types() -> None:
    implemented_command_types = {
        handler.command_type
        for handler in IMPLEMENTED_KNOWLEDGE_EXTRACTION_COMMAND_HANDLERS
    }

    assert implemented_command_types <= command_types_used_by_operations()


def test_schedule_claim_builder_section_work_is_implemented() -> None:
    command_type = (
        KnowledgeExtractionCanonicalCommandType.SCHEDULE_CLAIM_BUILDER_SECTION_WORK
    )

    assert is_command_implemented(command_type) is True
    assert implemented_handler_name_for(command_type) == (
        "HandleScheduleClaimBuilderSectionWorkCommandHandler"
    )


def test_prepare_claim_builder_dispatch_batch_is_implemented() -> None:
    command_type = (
        KnowledgeExtractionCanonicalCommandType.PREPARE_CLAIM_BUILDER_DISPATCH_BATCH
    )

    assert command_type in command_types_used_by_operations()
    assert is_command_implemented(command_type) is True
    assert implemented_handler_name_for(command_type) == (
        "HandlePrepareClaimBuilderDispatchBatchCommandHandler"
    )


def test_execute_claim_builder_section_is_implemented() -> None:
    command_type = KnowledgeExtractionCanonicalCommandType.EXECUTE_CLAIM_BUILDER_SECTION

    assert command_type in command_types_used_by_operations()
    assert is_command_implemented(command_type) is True
    assert implemented_handler_name_for(command_type) == (
        "HandleExecuteClaimBuilderSectionCommandHandler"
    )


def test_reconcile_claim_builder_progress_is_implemented() -> None:
    command_type = (
        KnowledgeExtractionCanonicalCommandType.RECONCILE_CLAIM_BUILDER_PROGRESS
    )

    assert command_type in command_types_used_by_operations()
    assert is_command_implemented(command_type) is True
    assert implemented_handler_name_for(command_type) == (
        "HandleReconcileClaimBuilderProgressCommandHandler"
    )


def test_apply_draft_claim_compaction_result_handler_is_registered() -> None:
    assert (
        implemented_handler_name_for(
            KnowledgeExtractionCanonicalCommandType.APPLY_DRAFT_CLAIM_COMPACTION_RESULT
        )
        == "HandleApplyDraftClaimCompactionResultCommandHandler"
    )


def test_reconcile_draft_claim_compaction_progress_handler_is_registered() -> None:
    assert (
        implemented_handler_name_for(
            KnowledgeExtractionCanonicalCommandType.RECONCILE_DRAFT_CLAIM_COMPACTION_PROGRESS
        )
        == "HandleReconcileDraftClaimCompactionProgressCommandHandler"
    )


def test_prepare_draft_claim_compaction_dispatch_batch_handler_is_registered() -> None:
    assert (
        implemented_handler_name_for(
            KnowledgeExtractionCanonicalCommandType.PREPARE_DRAFT_CLAIM_COMPACTION_DISPATCH_BATCH
        )
        == "HandlePrepareDraftClaimCompactionDispatchBatchCommandHandler"
    )
