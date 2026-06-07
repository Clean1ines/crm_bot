from __future__ import annotations

from src.domain.project_plane.knowledge_workbench.local_claim_graph import (
    local_claim_graph_from_claim_observations_payload,
)


def test_local_claim_graph_accepts_prompt_a_claim_without_local_triples() -> None:
    graph = local_claim_graph_from_claim_observations_payload(
        {
            "claim_observations": [
                {
                    "local_ref": "c1",
                    "claim": "Сервис помогает клиенту быстро получить ответ по документам.",
                    "claim_kind": "other",
                    "granularity": "atomic",
                    "triples": [],
                    "evidence_block": (
                        "Сервис помогает клиенту быстро получить ответ по документам."
                    ),
                    "possible_questions": ["Как быстро клиент получит ответ?"],
                    "scope": "",
                    "exclusion_scope": "",
                    "local_relations": [],
                    "confidence": 0.9,
                }
            ]
        },
        project_id="project-1",
        document_id="document-1",
        section_id="section-1",
        node_run_id="node-run-1",
    )

    assert len(graph.claims) == 1
    assert graph.claims[0].local_ref == "c1"
    assert graph.claims[0].claim_kind == "other"
    assert graph.claims[0].triples == ()
    assert graph.claims[0].local_relations == ()
    assert graph.claims[0].confidence == 0.9
