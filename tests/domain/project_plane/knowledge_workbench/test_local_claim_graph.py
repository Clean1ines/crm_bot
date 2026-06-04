import pytest

from src.domain.project_plane.knowledge_workbench import DomainInvariantError
from src.domain.project_plane.knowledge_workbench.local_claim_graph import (
    LocalClaimGraph,
    local_claim_graph_from_claim_observations_payload,
)


def _payload() -> dict[str, object]:
    return {
        "claim_observations": [
            {
                "local_ref": "c1",
                "claim": "CRM bot supports FAQ retrieval.",
                "claim_kind": "capability",
                "granularity": "atomic",
                "triples": [
                    {
                        "subject": "CRM bot",
                        "predicate": "has_capability",
                        "object": "FAQ retrieval",
                        "qualifiers": [],
                    }
                ],
                "evidence_block": "CRM bot can answer FAQ from uploaded documents.",
                "possible_questions": ["Can the bot answer FAQ?"],
                "scope": "FAQ documents",
                "exclusion_scope": "",
                "local_relations": [],
                "confidence": 0.92,
            }
        ]
    }


def test_local_claim_graph_from_claim_observations_payload_maps_extraction_material() -> (
    None
):
    graph = local_claim_graph_from_claim_observations_payload(
        _payload(),
        project_id="project-1",
        document_id="document-1",
        section_id="section-1",
        node_run_id="node-run-1",
    )

    assert isinstance(graph, LocalClaimGraph)
    assert graph.claims[0].local_ref == "c1"
    assert graph.claims[0].claim == "CRM bot supports FAQ retrieval."
    assert graph.claims[0].triples[0].predicate == "has_capability"
    assert graph.claims[0].possible_questions == ("Can the bot answer FAQ?",)
    assert graph.claims[0].local_relations == ()
    assert graph.claims[0].confidence == 0.92


def test_local_claim_graph_rejects_later_stage_fields_in_prompt_a_payload() -> None:
    payload = _payload()
    claims = payload["claim_observations"]
    assert isinstance(claims, list)
    claim = claims[0]
    assert isinstance(claim, dict)
    claim["suggested_" + "registry_action"] = "create_new_claim"

    with pytest.raises(DomainInvariantError, match="later-stage fields forbidden"):
        local_claim_graph_from_claim_observations_payload(
            payload,
            project_id="project-1",
            document_id="document-1",
            section_id="section-1",
            node_run_id="node-run-1",
        )


def test_local_claim_graph_requires_non_empty_claim_observations() -> None:
    with pytest.raises(DomainInvariantError, match="non-empty claim_observations"):
        local_claim_graph_from_claim_observations_payload(
            {"claim_observations": []},
            project_id="project-1",
            document_id="document-1",
            section_id="section-1",
            node_run_id="node-run-1",
        )


def test_local_claim_graph_requires_triples() -> None:
    payload = _payload()
    claims = payload["claim_observations"]
    assert isinstance(claims, list)
    claim = claims[0]
    assert isinstance(claim, dict)
    claim["triples"] = []

    with pytest.raises(DomainInvariantError, match="non-empty triples"):
        local_claim_graph_from_claim_observations_payload(
            payload,
            project_id="project-1",
            document_id="document-1",
            section_id="section-1",
            node_run_id="node-run-1",
        )
