from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.domain.project_plane.knowledge_workbench import (
    DomainInvariantError,
    RegistryUpdateOperation,
    RegistryUpdateProposal,
    RegistryUpdateProposalStatus,
    proposal_mutates_registry,
)


def test_registry_update_proposal_is_advisory_and_never_mutates_registry() -> None:
    proposal = RegistryUpdateProposal(
        proposal_id="proposal-1",
        node_run_id="node-run-1",
        processing_run_id="processing-run-1",
        project_id="00000000-0000-0000-0000-000000000001",
        document_id="document-1",
        section_id="section-1",
        operation=RegistryUpdateOperation.EXTEND,
        payload={"append_answer_delta": "new detail"},
        confidence=0.7,
        reason="LLM advisory update",
        status=RegistryUpdateProposalStatus.PROPOSED,
        created_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        target_fact_id="fact-1",
        source_claim_observation_id="claim-observation-1",
    )

    assert proposal_mutates_registry(proposal) is False


def test_registry_update_proposal_requires_section_id() -> None:
    with pytest.raises(DomainInvariantError, match="section_id"):
        RegistryUpdateProposal(
            proposal_id="proposal-1",
            node_run_id="node-run-1",
            processing_run_id="processing-run-1",
            project_id="00000000-0000-0000-0000-000000000001",
            document_id="document-1",
            section_id="",
            operation=RegistryUpdateOperation.CREATE,
            payload={},
            confidence=0.5,
            reason="missing section",
            status=RegistryUpdateProposalStatus.PROPOSED,
        )
