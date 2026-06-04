from __future__ import annotations

from dataclasses import dataclass

from .local_claim_retrieval import (
    LocalClaimCandidateGroup,
    LocalClaimSimilarityEdge,
)
from .local_claim_search import LocalClaimSearchDocument
from .shared import DomainInvariantError, JsonValue


@dataclass(frozen=True, slots=True)
class LocalClaimCanonicalizationMember:
    search_document_id: str
    project_id: str
    document_id: str
    local_ref: str
    section_id: str
    node_run_id: str
    claim: str
    claim_kind: str
    granularity: str
    triple_texts: tuple[str, ...]
    possible_questions: tuple[str, ...]
    scope: str
    exclusion_scope: str
    evidence_block: str
    relation_texts: tuple[str, ...]
    search_text: str

    def __post_init__(self) -> None:
        if not self.search_document_id.strip():
            raise DomainInvariantError(
                "canonicalization member requires search_document_id"
            )
        if not self.project_id.strip():
            raise DomainInvariantError("canonicalization member requires project_id")
        if not self.document_id.strip():
            raise DomainInvariantError("canonicalization member requires document_id")
        if not self.local_ref.strip():
            raise DomainInvariantError("canonicalization member requires local_ref")
        if not self.section_id.strip():
            raise DomainInvariantError("canonicalization member requires section_id")
        if not self.node_run_id.strip():
            raise DomainInvariantError("canonicalization member requires node_run_id")
        if not self.claim.strip():
            raise DomainInvariantError("canonicalization member requires claim")


@dataclass(frozen=True, slots=True)
class LocalClaimCanonicalizationEdge:
    source_search_document_id: str
    target_search_document_id: str
    score: float
    signal_summaries: tuple[dict[str, JsonValue], ...]

    def __post_init__(self) -> None:
        if not self.source_search_document_id.strip():
            raise DomainInvariantError(
                "canonicalization edge requires source_search_document_id"
            )
        if not self.target_search_document_id.strip():
            raise DomainInvariantError(
                "canonicalization edge requires target_search_document_id"
            )
        if self.source_search_document_id == self.target_search_document_id:
            raise DomainInvariantError("canonicalization edge cannot target itself")
        if self.score < 0 or self.score > 1:
            raise DomainInvariantError("canonicalization edge score must be in [0, 1]")


@dataclass(frozen=True, slots=True)
class LocalClaimCanonicalizationUnit:
    unit_id: str
    group_id: str
    members: tuple[LocalClaimCanonicalizationMember, ...]
    edges: tuple[LocalClaimCanonicalizationEdge, ...]
    max_similarity_score: float

    def __post_init__(self) -> None:
        if not self.unit_id.strip():
            raise DomainInvariantError("canonicalization unit requires unit_id")
        if not self.group_id.strip():
            raise DomainInvariantError("canonicalization unit requires group_id")
        if not self.members:
            raise DomainInvariantError("canonicalization unit requires members")
        member_ids = tuple(member.search_document_id for member in self.members)
        if len(set(member_ids)) != len(member_ids):
            raise DomainInvariantError("canonicalization unit has duplicate members")
        member_id_set = set(member_ids)
        for edge in self.edges:
            if edge.source_search_document_id not in member_id_set:
                raise DomainInvariantError(
                    "canonicalization edge source must belong to unit"
                )
            if edge.target_search_document_id not in member_id_set:
                raise DomainInvariantError(
                    "canonicalization edge target must belong to unit"
                )
        if self.max_similarity_score < 0 or self.max_similarity_score > 1:
            raise DomainInvariantError(
                "canonicalization unit max_similarity_score must be in [0, 1]"
            )

    @property
    def member_count(self) -> int:
        return len(self.members)

    @property
    def edge_count(self) -> int:
        return len(self.edges)

    def to_prompt_payload(self) -> dict[str, JsonValue]:
        return {
            "unit_id": self.unit_id,
            "group_id": self.group_id,
            "max_similarity_score": self.max_similarity_score,
            "members": [
                {
                    "search_document_id": member.search_document_id,
                    "project_id": member.project_id,
                    "document_id": member.document_id,
                    "local_ref": member.local_ref,
                    "section_id": member.section_id,
                    "node_run_id": member.node_run_id,
                    "claim": member.claim,
                    "claim_kind": member.claim_kind,
                    "granularity": member.granularity,
                    "triples": list(member.triple_texts),
                    "possible_questions": list(member.possible_questions),
                    "scope": member.scope,
                    "exclusion_scope": member.exclusion_scope,
                    "evidence_block": member.evidence_block,
                    "local_relations": list(member.relation_texts),
                    "search_text": member.search_text,
                }
                for member in self.members
            ],
            "similarity_edges": [
                {
                    "source_search_document_id": edge.source_search_document_id,
                    "target_search_document_id": edge.target_search_document_id,
                    "score": edge.score,
                    "signals": list(edge.signal_summaries),
                }
                for edge in self.edges
            ],
        }


def local_claim_canonicalization_units_from_retrieval(
    *,
    search_documents: tuple[LocalClaimSearchDocument, ...],
    candidate_groups: tuple[LocalClaimCandidateGroup, ...],
    similarity_edges: tuple[LocalClaimSimilarityEdge, ...],
) -> tuple[LocalClaimCanonicalizationUnit, ...]:
    documents_by_id = {
        document.search_document_id: document for document in search_documents
    }
    edges_by_group_members: dict[frozenset[str], list[LocalClaimSimilarityEdge]] = {}

    for group in candidate_groups:
        group_member_ids = frozenset(group.search_document_ids)
        edges_by_group_members[group_member_ids] = [
            edge
            for edge in similarity_edges
            if edge.source_search_document_id in group_member_ids
            and edge.target_search_document_id in group_member_ids
        ]

    units: list[LocalClaimCanonicalizationUnit] = []
    for index, group in enumerate(candidate_groups, start=1):
        members: list[LocalClaimCanonicalizationMember] = []
        for search_document_id in group.search_document_ids:
            document = documents_by_id.get(search_document_id)
            if document is None:
                raise DomainInvariantError(
                    f"canonicalization group references unknown search document: {search_document_id}"
                )
            members.append(_member_from_search_document(document))

        group_edges = edges_by_group_members[frozenset(group.search_document_ids)]
        units.append(
            LocalClaimCanonicalizationUnit(
                unit_id=f"canonicalization-unit-{index}",
                group_id=group.group_id,
                members=tuple(members),
                edges=tuple(_edge_from_similarity_edge(edge) for edge in group_edges),
                max_similarity_score=group.max_score,
            )
        )

    return tuple(units)


def _member_from_search_document(
    document: LocalClaimSearchDocument,
) -> LocalClaimCanonicalizationMember:
    return LocalClaimCanonicalizationMember(
        search_document_id=document.search_document_id,
        project_id=str(document.project_id),
        document_id=str(document.document_id),
        local_ref=document.local_ref,
        section_id=str(document.section_id),
        node_run_id=str(document.node_run_id),
        claim=document.claim,
        claim_kind=document.claim_kind,
        granularity=document.granularity,
        triple_texts=document.triple_texts,
        possible_questions=document.possible_questions,
        scope=document.scope,
        exclusion_scope=document.exclusion_scope,
        evidence_block=document.evidence_block,
        relation_texts=document.relation_texts,
        search_text=document.search_text,
    )


def _edge_from_similarity_edge(
    edge: LocalClaimSimilarityEdge,
) -> LocalClaimCanonicalizationEdge:
    return LocalClaimCanonicalizationEdge(
        source_search_document_id=edge.source_search_document_id,
        target_search_document_id=edge.target_search_document_id,
        score=edge.score,
        signal_summaries=tuple(
            {
                "signal_type": signal.signal_type,
                "score": signal.score,
                "matched_values": list(signal.matched_values),
            }
            for signal in edge.signals
        ),
    )


__all__ = [
    "LocalClaimCanonicalizationEdge",
    "LocalClaimCanonicalizationMember",
    "LocalClaimCanonicalizationUnit",
    "local_claim_canonicalization_units_from_retrieval",
]
