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
_EPSILON = 1e-9


@dataclass(frozen=True, slots=True)
class DraftClaimHybridSimilarityPolicy:
    """Recall-oriented pre-LLM candidate edge policy.

    This stage only finds draft claims that are similar enough to compare in the
    following LLM compaction phase. It does not assign final topics and does not
    decide canonical entries.

    Vector score is affine-normalized cosine:
        normalized = (raw_cosine + 1.0) / 2.0
    """

    threshold: float = 0.78
    strong_vector_threshold: float = 0.925
    supported_vector_threshold: float = 0.910
    review_vector_threshold: float = 0.900
    weak_support_threshold: float = 0.05
    question_bridge_threshold: float = 0.10
    lexical_bridge_threshold: float = 0.15
    strong_exclusion_threshold: float = 0.20

    def build_edges(
        self,
        claims: tuple[DraftClaimForCompaction, ...],
    ) -> tuple[DraftClaimCompactionEdgeCandidate, ...]:
        ordered = tuple(sorted(claims, key=lambda claim: claim.observation_ref))
        edges: list[DraftClaimCompactionEdgeCandidate] = []
        for index, left in enumerate(ordered):
            for right in ordered[index + 1 :]:
                edge = self._build_edge(left, right)
                if edge.signals["admitted_by_policy"] is True:
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
        granularity_score = 1.0 if left.granularity == right.granularity else 0.5
        weighted_score = _clamp(
            vector_score * 0.62
            + lexical_score * 0.16
            + question_score * 0.16
            + exclusion_score * 0.04
            + granularity_score * 0.02
        )
        admission = self._admission_decision(
            vector_score=vector_score,
            lexical_score=lexical_score,
            question_score=question_score,
            exclusion_score=exclusion_score,
        )
        combined = (
            max(weighted_score, vector_score) if admission.admitted else weighted_score
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
                "algorithm": "draft_claim_compaction_candidate_similarity_v3",
                "policy_version": "simple_candidate_clustering_v1",
                "score_space": "affine_normalized_cosine_v1",
                "raw_cosine_score": _raw_cosine_from_normalized(vector_score),
                "normalized_vector_score": vector_score,
                "vector_score": vector_score,
                "lexical_score": lexical_score,
                "question_overlap_score": question_score,
                "exclusion_scope_score": exclusion_score,
                "granularity_score": granularity_score,
                "weighted_score": weighted_score,
                "combined_score": combined,
                "admitted_by_policy": admission.admitted,
                "edge_kind": admission.edge_kind,
                "admission_reason": admission.reason,
                "threshold": self.threshold,
                "strong_vector_threshold": self.strong_vector_threshold,
                "supported_vector_threshold": self.supported_vector_threshold,
                "review_vector_threshold": self.review_vector_threshold,
                "weak_support_threshold": self.weak_support_threshold,
                "question_bridge_threshold": self.question_bridge_threshold,
                "lexical_bridge_threshold": self.lexical_bridge_threshold,
                "strong_exclusion_threshold": self.strong_exclusion_threshold,
            },
        )

    def _admission_decision(
        self,
        *,
        vector_score: float,
        lexical_score: float,
        question_score: float,
        exclusion_score: float,
    ) -> "_AdmissionDecision":
        if _meets_threshold(vector_score, self.strong_vector_threshold):
            return _AdmissionDecision(
                admitted=True,
                edge_kind="vector_candidate",
                reason="vector similarity is high enough for candidate compaction clustering",
            )

        weak_support = (
            lexical_score >= self.weak_support_threshold
            or question_score >= self.weak_support_threshold
            or exclusion_score >= self.weak_support_threshold
        )
        if (
            _meets_threshold(vector_score, self.supported_vector_threshold)
            and weak_support
        ):
            return _AdmissionDecision(
                admitted=True,
                edge_kind="surface_supported_vector_candidate",
                reason="vector similarity is good and at least one surface signal supports the edge",
            )

        strong_support = (
            lexical_score >= self.lexical_bridge_threshold
            or question_score >= self.question_bridge_threshold
            or exclusion_score >= self.strong_exclusion_threshold
        )
        if (
            _meets_threshold(vector_score, self.review_vector_threshold)
            and strong_support
        ):
            return _AdmissionDecision(
                admitted=True,
                edge_kind="review_candidate",
                reason="vector similarity is review-level but surface overlap is strong enough for LLM comparison",
            )

        return _AdmissionDecision(
            admitted=False,
            edge_kind="not_admitted",
            reason="insufficient vector/surface support for candidate compaction clustering",
        )


@dataclass(frozen=True, slots=True)
class _AdmissionDecision:
    admitted: bool
    edge_kind: str
    reason: str


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


def _meets_threshold(value: float, threshold: float) -> bool:
    return value + _EPSILON >= threshold


def _ref(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256(":".join(parts).encode("utf-8")).hexdigest()
    return f"{prefix}:{digest}"


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _raw_cosine_from_normalized(value: float) -> float:
    return max(-1.0, min(1.0, value * 2.0 - 1.0))
