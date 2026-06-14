from __future__ import annotations

import hashlib
from dataclasses import dataclass

from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_models import (
    DraftClaimCompactionEdgeCandidate,
    DraftClaimCompactionGroupCandidate,
    DraftClaimForCompaction,
)


@dataclass(frozen=True, slots=True)
class DraftClaimCompactionGroupingPolicy:
    group_algorithm: str = "hybrid_connected_components_v1"
    group_threshold: float = 0.78

    def build_groups(
        self,
        claims: tuple[DraftClaimForCompaction, ...],
        edges: tuple[DraftClaimCompactionEdgeCandidate, ...],
    ) -> tuple[DraftClaimCompactionGroupCandidate, ...]:
        by_ref = {claim.observation_ref: claim for claim in claims}
        graph: dict[str, set[str]] = {ref: set() for ref in by_ref}
        for edge in edges:
            if edge.combined_score >= self.group_threshold:
                graph[edge.left_observation_ref].add(edge.right_observation_ref)
                graph[edge.right_observation_ref].add(edge.left_observation_ref)
        groups: list[DraftClaimCompactionGroupCandidate] = []
        seen: set[str] = set()
        for ref in sorted(by_ref):
            if ref in seen:
                continue
            members = _component(ref, graph)
            seen.update(members)
            claims_in_group = tuple(by_ref[item] for item in sorted(members))
            refs = tuple(claim.observation_ref for claim in claims_in_group)
            groups.append(
                DraftClaimCompactionGroupCandidate(
                    group_ref=_ref(
                        "draft-claim-compaction-group",
                        by_ref[ref].workflow_run_id,
                        *refs,
                    ),
                    workflow_run_id=by_ref[ref].workflow_run_id,
                    source_document_ref=by_ref[ref].source_document_ref,
                    embedding_model_id=by_ref[ref].embedding_model_id,
                    group_algorithm=self.group_algorithm,
                    group_threshold=self.group_threshold,
                    member_observation_refs=refs,
                    member_embedding_refs=tuple(
                        claim.embedding_ref for claim in claims_in_group
                    ),
                    member_source_unit_refs=tuple(
                        claim.source_unit_ref for claim in claims_in_group
                    ),
                    estimated_input_tokens=0,
                    requires_split=False,
                )
            )
        return tuple(sorted(groups, key=lambda group: group.group_ref))


def _component(start: str, graph: dict[str, set[str]]) -> set[str]:
    found: set[str] = set()
    pending = [start]
    while pending:
        current = pending.pop()
        if current in found:
            continue
        found.add(current)
        pending.extend(sorted(graph[current] - found, reverse=True))
    return found


def _ref(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256(":".join(parts).encode("utf-8")).hexdigest()
    return f"{prefix}:{digest}"
