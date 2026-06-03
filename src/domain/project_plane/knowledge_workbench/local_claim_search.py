from __future__ import annotations

from dataclasses import dataclass

from .local_claim_graph import LocalClaim, LocalClaimGraph
from .shared import (
    DocumentId,
    DomainInvariantError,
    NodeRunId,
    ProjectId,
    SectionId,
)


@dataclass(frozen=True, slots=True)
class LocalClaimSearchDocument:
    search_document_id: str
    project_id: ProjectId
    document_id: DocumentId
    section_id: SectionId
    node_run_id: NodeRunId
    local_ref: str
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
                "local claim search document id is required"
            )
        if not str(self.project_id).strip():
            raise DomainInvariantError(
                "local claim search document project_id is required"
            )
        if not str(self.document_id).strip():
            raise DomainInvariantError(
                "local claim search document document_id is required"
            )
        if not str(self.section_id).strip():
            raise DomainInvariantError(
                "local claim search document section_id is required"
            )
        if not str(self.node_run_id).strip():
            raise DomainInvariantError(
                "local claim search document node_run_id is required"
            )
        if not self.local_ref.strip():
            raise DomainInvariantError(
                "local claim search document local_ref is required"
            )
        if not self.claim.strip():
            raise DomainInvariantError(
                "local claim search document claim is required"
            )
        if not self.search_text.strip():
            raise DomainInvariantError(
                "local claim search document search_text is required"
            )


def local_claim_search_document_from_claim(
    *,
    graph: LocalClaimGraph,
    claim: LocalClaim,
) -> LocalClaimSearchDocument:
    triple_texts = tuple(
        _triple_text(
            subject=triple.subject,
            predicate=triple.predicate,
            object_=triple.object,
        )
        for triple in claim.triples
    )
    relation_texts = tuple(
        _relation_text(
            target_ref=relation.target_ref,
            relation=relation.relation,
            reason=relation.reason,
        )
        for relation in claim.local_relations
    )
    search_text = _search_text(
        claim=claim,
        triple_texts=triple_texts,
        relation_texts=relation_texts,
    )

    return LocalClaimSearchDocument(
        search_document_id=_search_document_id(
            section_id=str(graph.section_id),
            node_run_id=str(graph.node_run_id),
            local_ref=claim.local_ref,
        ),
        project_id=graph.project_id,
        document_id=graph.document_id,
        section_id=graph.section_id,
        node_run_id=graph.node_run_id,
        local_ref=claim.local_ref,
        claim=claim.claim,
        claim_kind=claim.claim_kind,
        granularity=claim.granularity,
        triple_texts=triple_texts,
        possible_questions=claim.possible_questions,
        scope=claim.scope,
        exclusion_scope=claim.exclusion_scope,
        evidence_block=claim.evidence.evidence_block,
        relation_texts=relation_texts,
        search_text=search_text,
    )


def local_claim_search_documents_from_graph(
    graph: LocalClaimGraph,
) -> tuple[LocalClaimSearchDocument, ...]:
    return tuple(
        local_claim_search_document_from_claim(graph=graph, claim=claim)
        for claim in graph.claims
    )


def local_claim_search_documents_from_graphs(
    graphs: tuple[LocalClaimGraph, ...],
) -> tuple[LocalClaimSearchDocument, ...]:
    documents: list[LocalClaimSearchDocument] = []
    for graph in graphs:
        documents.extend(local_claim_search_documents_from_graph(graph))
    return tuple(documents)


def _search_document_id(
    *,
    section_id: str,
    node_run_id: str,
    local_ref: str,
) -> str:
    return f"{section_id}:{node_run_id}:{local_ref}"


def _triple_text(
    *,
    subject: str,
    predicate: str,
    object_: str,
) -> str:
    return f"{subject} {predicate} {object_}"


def _relation_text(
    *,
    target_ref: str,
    relation: str,
    reason: str,
) -> str:
    return f"{relation} -> {target_ref}: {reason}"


def _search_text(
    *,
    claim: LocalClaim,
    triple_texts: tuple[str, ...],
    relation_texts: tuple[str, ...],
) -> str:
    parts: list[str] = [
        f"claim: {claim.claim}",
        f"claim_kind: {claim.claim_kind}",
        f"granularity: {claim.granularity}",
    ]

    if triple_texts:
        parts.append("triples:")
        parts.extend(f"- {item}" for item in triple_texts)

    if claim.possible_questions:
        parts.append("possible_questions:")
        parts.extend(f"- {item}" for item in claim.possible_questions)

    if claim.scope.strip():
        parts.append(f"scope: {claim.scope}")

    if claim.exclusion_scope.strip():
        parts.append(f"exclusion_scope: {claim.exclusion_scope}")

    if claim.evidence.evidence_block.strip():
        parts.append(f"evidence: {claim.evidence.evidence_block}")

    if relation_texts:
        parts.append("local_relations:")
        parts.extend(f"- {item}" for item in relation_texts)

    return "\n".join(parts)


__all__ = [
    "LocalClaimSearchDocument",
    "local_claim_search_document_from_claim",
    "local_claim_search_documents_from_graph",
    "local_claim_search_documents_from_graphs",
]
