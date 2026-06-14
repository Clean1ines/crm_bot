from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass

from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_models import (
    DraftClaimCompactionEdgeCandidate,
    DraftClaimForCompaction,
)

_TOKEN_RE = re.compile(r"[a-zA-Zа-яА-ЯёЁ0-9]+")


@dataclass(frozen=True, slots=True)
class DraftClaimHybridSimilarityPolicy:
    threshold: float = 0.78

    def build_edges(
        self,
        claims: tuple[DraftClaimForCompaction, ...],
    ) -> tuple[DraftClaimCompactionEdgeCandidate, ...]:
        ordered = tuple(sorted(claims, key=lambda claim: claim.observation_ref))
        edges: list[DraftClaimCompactionEdgeCandidate] = []
        for index, left in enumerate(ordered):
            for right in ordered[index + 1 :]:
                edge = self._build_edge(left, right)
                if edge.combined_score >= self.threshold:
                    edges.append(edge)
        return tuple(
            sorted(edges, key=lambda edge: (-edge.combined_score, edge.edge_ref))
        )

    def _build_edge(
        self,
        left: DraftClaimForCompaction,
        right: DraftClaimForCompaction,
    ) -> DraftClaimCompactionEdgeCandidate:
        vector_score = _cosine(left.vector, right.vector)
        lexical_score = _jaccard(_tokens((left.claim,)), _tokens((right.claim,)))
        question_score = _jaccard(
            _tokens(left.possible_questions),
            _tokens(right.possible_questions),
        )
        exclusion_score = _jaccard(
            _tokens(left.exclusion_scope), _tokens(right.exclusion_scope)
        )
        if not left.exclusion_scope and not right.exclusion_scope:
            exclusion_score = 0.5
        granularity_score = 1.0 if left.granularity == right.granularity else 0.5
        combined = _clamp(
            vector_score * 0.62
            + lexical_score * 0.16
            + question_score * 0.16
            + exclusion_score * 0.04
            + granularity_score * 0.02
        )
        return DraftClaimCompactionEdgeCandidate(
            edge_ref=_ref(
                "draft-claim-compaction-edge",
                left.workflow_run_id,
                left.observation_ref,
                right.observation_ref,
            ),
            workflow_run_id=left.workflow_run_id,
            source_document_ref=left.source_document_ref,
            left_observation_ref=left.observation_ref,
            right_observation_ref=right.observation_ref,
            left_embedding_ref=left.embedding_ref,
            right_embedding_ref=right.embedding_ref,
            vector_score=vector_score,
            lexical_score=lexical_score,
            question_overlap_score=question_score,
            exclusion_scope_score=exclusion_score,
            granularity_score=granularity_score,
            combined_score=combined,
            signals={
                "algorithm": "hybrid_draft_claim_similarity_v1",
                "vector_score": vector_score,
                "lexical_score": lexical_score,
                "question_overlap_score": question_score,
                "exclusion_scope_score": exclusion_score,
                "granularity_score": granularity_score,
                "combined_score": combined,
            },
        )


def _tokens(values: tuple[str, ...]) -> frozenset[str]:
    result: set[str] = set()
    for value in values:
        result.update(match.group(0).casefold() for match in _TOKEN_RE.finditer(value))
    return frozenset(token for token in result if len(token) > 1)


def _jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if len(left) != len(right):
        raise ValueError("vectors must have equal dimensions")
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return _clamp((dot / (left_norm * right_norm) + 1.0) / 2.0)


def _ref(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256(":".join(parts).encode("utf-8")).hexdigest()
    return f"{prefix}:{digest}"


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
