from __future__ import annotations

from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalCommandType,
)
from src.contexts.knowledge_workbench.application.sagas.repair_knowledge_extraction_command_payload import (
    repair_knowledge_extraction_command_payload,
)
from tests.contexts.knowledge_workbench.application.sagas.test_dispatch_knowledge_extraction_workflow_command import (
    _workflow_command,
    _workflow_run_id,
)


def test_repairs_compaction_prepare_command_without_dispatch_preparation() -> None:
    command = _workflow_command(
        KnowledgeExtractionCanonicalCommandType.PREPARE_DRAFT_CLAIM_COMPACTION_DISPATCH_BATCH,
        payload={
            "workflow_run_id": _workflow_run_id(),
            "scheduled_work_item_count": 3,
        },
    )

    repaired = repair_knowledge_extraction_command_payload(
        workflow_command=command,
        command_type=(
            KnowledgeExtractionCanonicalCommandType.PREPARE_DRAFT_CLAIM_COMPACTION_DISPATCH_BATCH
        ),
    )

    dispatch_preparation = repaired.payload["llm_dispatch_preparation"]
    assert isinstance(dispatch_preparation, dict)
    assert dispatch_preparation["active_model_ref"] == "openai/gpt-oss-120b"
    assert dispatch_preparation["requested_items"] == 3
    assert dispatch_preparation["worker_ref"] == (
        "knowledge-workbench-draft-claim-compaction-dispatch"
    )
    assert dispatch_preparation["lease_token_prefix"] == (
        f"draft-claim-compaction-dispatch:{_workflow_run_id()}"
    )
    assert dispatch_preparation["profile"] == {
        "profile_id": "draft_claim_compaction",
        "estimated_prompt_tokens": 90000,
        "estimated_completion_tokens": 4000,
        "estimated_requests": 1,
    }


def test_does_not_mask_malformed_explicit_dispatch_preparation() -> None:
    command = _workflow_command(
        KnowledgeExtractionCanonicalCommandType.PREPARE_CLAIM_BUILDER_DISPATCH_BATCH,
        payload={
            "workflow_run_id": _workflow_run_id(),
            "scheduled_work_item_count": 1,
            "llm_dispatch_preparation": "not-a-mapping",
        },
    )

    repaired = repair_knowledge_extraction_command_payload(
        workflow_command=command,
        command_type=(
            KnowledgeExtractionCanonicalCommandType.PREPARE_CLAIM_BUILDER_DISPATCH_BATCH
        ),
    )

    assert repaired is command
    assert repaired.payload["llm_dispatch_preparation"] == "not-a-mapping"
