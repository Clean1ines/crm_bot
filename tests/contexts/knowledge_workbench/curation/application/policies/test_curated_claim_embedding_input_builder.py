from __future__ import annotations

from datetime import datetime, timezone

from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_prompt_contract import (
    DraftClaimCompactionMergeDecision,
    DraftClaimCompactionTriplePredicate,
)
from src.contexts.knowledge_workbench.curation.application.models.draft_claim_curation_workspace import (
    DraftClaimCurationItemEditablePayload,
    DraftClaimCurationWorkspaceItem,
)
from src.contexts.knowledge_workbench.curation.application.policies.curated_claim_embedding_input_builder import (
    CuratedClaimEmbeddingInputBuilder,
)


def _valid_predicate() -> str:
    return next(iter(DraftClaimCompactionTriplePredicate)).value


def _valid_merge_decision() -> str:
    return next(iter(DraftClaimCompactionMergeDecision)).value


def _item() -> DraftClaimCurationWorkspaceItem:
    payload = {
        "key": "edited-key",
        "claim": "Edited claim",
        "claim_kind": "definition",
        "granularity": "atomic",
        "source_claim_refs": ["raw-1"],
        "triples": [
            {
                "subject": "A",
                "predicate": _valid_predicate(),
                "object": "B",
                "qualifiers": ["q"],
            }
        ],
        "merge_decision": _valid_merge_decision(),
        "possible_questions": ["What is B?"],
        "exclusion_scope": "Not C",
        "evidence_block": "Evidence text",
    }
    editable = DraftClaimCurationItemEditablePayload.from_payload(payload)
    return DraftClaimCurationWorkspaceItem(
        item_ref="item-1",
        workspace_ref="workspace-1",
        workflow_run_id="workflow-1",
        group_ref="group-1",
        compacted_node_ref="compacted-1",
        source_claim_refs=("raw-1",),
        original_payload=editable,
        editable_payload=editable,
        excluded=False,
        exclusion_reason=None,
        created_at=datetime(2026, 6, 15, tzinfo=timezone.utc),
        updated_at=datetime(2026, 6, 15, tzinfo=timezone.utc),
    )


def test_builder_uses_editable_payload_and_stable_sections() -> None:
    result = CuratedClaimEmbeddingInputBuilder().build((_item(),))

    assert len(result) == 1
    text = result[0].text
    assert "Claim:\nEdited claim" in text
    assert "Possible questions:\n- What is B?" in text
    assert "Exclusion scope:\nNot C" in text
    assert "Evidence:\nEvidence text" in text
    assert f'"predicate":"{_valid_predicate()}"' in text
    assert result[0].text_hash
