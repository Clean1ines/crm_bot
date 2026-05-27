from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal, TypeAlias

SurfaceKind: TypeAlias = Literal[
    "umbrella",
    "child",
    "specific",
    "standalone",
    "procedural",
    "safety",
    "pricing",
    "integration",
    "handoff",
    "definition",
    "curation",
    "retrieval_quality",
    "service_limits",
    "other",
]
SurfaceRelationType: TypeAlias = Literal[
    "umbrella_contains",
    "specializes",
    "sibling",
    "overlaps",
    "duplicates",
    "near_duplicate",
    "contradicts",
    "unrelated",
    "split_needed",
    "needs_new_parent",
    "reparent_needed",
]
SameSurfaceEvidenceType: TypeAlias = Literal[
    "supplemented_by",
    "incomplete_version_of",
    "same_knowledge",
]
QuestionKind: TypeAlias = Literal[
    "overview",
    "narrow",
    "faq_question",
    "test_question",
    "generated_variant",
    "user_like_question",
    "expected_topic_hint",
]
MergeType: TypeAlias = Literal[
    "supplemented_knowledge",
    "incomplete_evidence_absorbed",
    "same_knowledge",
]


@dataclass(frozen=True, slots=True)
class SurfaceCandidate:
    key: str
    title: str
    kind: SurfaceKind
    source_unit_key: str
    answer_scope: str
    question_scope: str
    exclusion_scope: str
    source_refs: tuple[str, ...] = ()
    answer: str = ""


@dataclass(frozen=True, slots=True)
class SurfaceRelation:
    parent_key: str
    child_key: str
    relation_type: SurfaceRelationType
    confidence: float = 1.0
    reason: str = ""
    source_refs: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SameSurfaceEvidence:
    source_key: str
    target_key: str
    evidence_type: SameSurfaceEvidenceType


SameSurfaceEvidenceInput: TypeAlias = (
    SameSurfaceEvidence | tuple[str, str, SameSurfaceEvidenceType]
)


@dataclass(frozen=True, slots=True)
class QuestionOwnership:
    surface_key: str
    question: str
    kind: QuestionKind


@dataclass(frozen=True, slots=True)
class MergedSurface:
    canonical_key: str
    absorbed_keys: frozenset[str]
    merge_type: MergeType


@dataclass(frozen=True, slots=True)
class SurfaceNode:
    key: str
    title: str
    kind: SurfaceKind
    answer_scope: str
    question_scope: str
    exclusion_scope: str
    answer: str
    parent_keys: tuple[str, ...] = ()
    child_keys: tuple[str, ...] = ()
    absorbed_keys: frozenset[str] = field(default_factory=frozenset)
    source_refs: tuple[str, ...] = ()
    owned_questions: tuple[QuestionOwnership, ...] = ()

    def answer_mentions(self, term: str) -> bool:
        needle = term.casefold()
        haystack = "\n".join(
            (
                self.title,
                self.answer,
                self.answer_scope,
                self.question_scope,
            )
        ).casefold()
        return needle in haystack

    def answers_narrow_question_about(self, term: str) -> bool:
        needle = term.casefold()
        return any(
            question.kind == "narrow" and needle in question.question.casefold()
            for question in self.owned_questions
        )


@dataclass(frozen=True, slots=True)
class ReconciledSurfaceGraph:
    surfaces: dict[str, SurfaceNode]
    relations: tuple[SurfaceRelation, ...]
    merged_surfaces: tuple[MergedSurface, ...]
    question_ownership: tuple[QuestionOwnership, ...]

    def surface(self, key: str) -> SurfaceNode:
        return self.surfaces[key]

    def has_relation(
        self,
        parent_key: str,
        child_key: str,
        relation_type: SurfaceRelationType,
    ) -> bool:
        return any(
            relation.parent_key == parent_key
            and relation.child_key == child_key
            and relation.relation_type == relation_type
            for relation in self.relations
        )

    def has_merged_surface(
        self,
        *,
        canonical_key: str,
        absorbed_keys: set[str],
        merge_type: MergeType,
    ) -> bool:
        return any(
            merged.canonical_key == canonical_key
            and merged.absorbed_keys == frozenset(absorbed_keys)
            and merged.merge_type == merge_type
            for merged in self.merged_surfaces
        )

    def questions_for(self, surface_key: str) -> set[str]:
        return {
            ownership.question
            for ownership in self.question_ownership
            if ownership.surface_key == surface_key
        }


def reconcile_surface_graph(
    *,
    candidates: Sequence[SurfaceCandidate],
    local_relations: Sequence[SurfaceRelation],
    same_surface_evidence: Sequence[SameSurfaceEvidenceInput],
    initial_questions: Sequence[QuestionOwnership],
) -> ReconciledSurfaceGraph:
    """Build a deterministic retrieval-surface graph from local evidence.

    This function is deliberately pure domain logic: no DB, no LLM, no HTTP.
    It captures the graph invariants that the staged FAQ pipeline must preserve:
    late umbrella reparenting, same-surface merges, and non-overlapping parent/child
    question ownership.
    """

    candidates_by_key = {candidate.key: candidate for candidate in candidates}
    canonical_key_by_key = {candidate.key: candidate.key for candidate in candidates}
    synthetic_candidates: dict[str, SurfaceCandidate] = {}
    merged_surfaces: list[MergedSurface] = []

    for evidence in same_surface_evidence:
        normalized = _normalize_same_surface_evidence(evidence)
        match normalized.evidence_type:
            case "supplemented_by":
                canonical_key_by_key[normalized.source_key] = normalized.target_key
                merged_surfaces.append(
                    MergedSurface(
                        canonical_key=normalized.target_key,
                        absorbed_keys=frozenset({normalized.source_key}),
                        merge_type="supplemented_knowledge",
                    )
                )
            case "incomplete_version_of":
                canonical_key_by_key[normalized.source_key] = normalized.target_key
                merged_surfaces.append(
                    MergedSurface(
                        canonical_key=normalized.target_key,
                        absorbed_keys=frozenset({normalized.source_key}),
                        merge_type="incomplete_evidence_absorbed",
                    )
                )
            case "same_knowledge":
                canonical_key = _same_knowledge_canonical_key(
                    normalized.source_key,
                    normalized.target_key,
                )
                synthetic_candidates[canonical_key] = _merge_same_knowledge_candidate(
                    canonical_key=canonical_key,
                    left=candidates_by_key[normalized.source_key],
                    right=candidates_by_key[normalized.target_key],
                )
                canonical_key_by_key[normalized.source_key] = canonical_key
                canonical_key_by_key[normalized.target_key] = canonical_key
                merged_surfaces.append(
                    MergedSurface(
                        canonical_key=canonical_key,
                        absorbed_keys=frozenset(
                            {normalized.source_key, normalized.target_key}
                        ),
                        merge_type="same_knowledge",
                    )
                )

    canonical_candidates = _canonical_candidates(
        candidates_by_key=candidates_by_key,
        synthetic_candidates=synthetic_candidates,
        canonical_key_by_key=canonical_key_by_key,
    )
    relations = _canonical_relations(
        local_relations=local_relations,
        canonical_key_by_key=canonical_key_by_key,
    )
    question_ownership = _canonical_question_ownership(
        initial_questions=initial_questions,
        canonical_key_by_key=canonical_key_by_key,
    )

    parent_keys_by_child, child_keys_by_parent = _relation_indexes(relations)
    surfaces = _build_surface_nodes(
        canonical_candidates=canonical_candidates,
        parent_keys_by_child=parent_keys_by_child,
        child_keys_by_parent=child_keys_by_parent,
        merged_surfaces=merged_surfaces,
        question_ownership=question_ownership,
    )
    return ReconciledSurfaceGraph(
        surfaces=surfaces,
        relations=relations,
        merged_surfaces=tuple(merged_surfaces),
        question_ownership=question_ownership,
    )


def _normalize_same_surface_evidence(
    evidence: SameSurfaceEvidenceInput,
) -> SameSurfaceEvidence:
    if isinstance(evidence, SameSurfaceEvidence):
        return evidence
    source_key, target_key, evidence_type = evidence
    return SameSurfaceEvidence(
        source_key=source_key,
        target_key=target_key,
        evidence_type=evidence_type,
    )


def _same_knowledge_canonical_key(left_key: str, right_key: str) -> str:
    if left_key.endswith("_prime"):
        return f"{left_key.removesuffix('_prime')}_merged"
    if right_key.endswith("_prime"):
        return f"{right_key.removesuffix('_prime')}_merged"
    return f"{left_key}_merged"


def _merge_same_knowledge_candidate(
    *,
    canonical_key: str,
    left: SurfaceCandidate,
    right: SurfaceCandidate,
) -> SurfaceCandidate:
    return SurfaceCandidate(
        key=canonical_key,
        title=f"{left.title}*{right.title}",
        kind=_narrowest_kind(left.kind, right.kind),
        source_unit_key=left.source_unit_key,
        answer_scope=f"{left.answer_scope}\n{right.answer_scope}",
        question_scope=f"{left.question_scope}\n{right.question_scope}",
        exclusion_scope=f"{left.exclusion_scope}\n{right.exclusion_scope}",
        source_refs=left.source_refs + right.source_refs,
        answer=(left.answer or left.answer_scope),
    )


def _narrowest_kind(left: SurfaceKind, right: SurfaceKind) -> SurfaceKind:
    if "child" in {left, right}:
        return "child"
    if "specific" in {left, right}:
        return "specific"
    if left == right:
        return left
    return "specific"


def _canonical_candidates(
    *,
    candidates_by_key: dict[str, SurfaceCandidate],
    synthetic_candidates: dict[str, SurfaceCandidate],
    canonical_key_by_key: dict[str, str],
) -> dict[str, SurfaceCandidate]:
    canonical_candidates = dict(synthetic_candidates)
    absorbed_keys = {
        key
        for key, canonical_key in canonical_key_by_key.items()
        if key != canonical_key
    }
    for key, candidate in candidates_by_key.items():
        canonical_key = canonical_key_by_key[key]
        if key in absorbed_keys:
            continue
        canonical_candidates[canonical_key] = candidate
    return canonical_candidates


def _canonical_relations(
    *,
    local_relations: Sequence[SurfaceRelation],
    canonical_key_by_key: dict[str, str],
) -> tuple[SurfaceRelation, ...]:
    relations_by_identity: dict[
        tuple[str, str, SurfaceRelationType], SurfaceRelation
    ] = {}
    for relation in local_relations:
        parent_key = canonical_key_by_key.get(relation.parent_key, relation.parent_key)
        child_key = canonical_key_by_key.get(relation.child_key, relation.child_key)
        if parent_key == child_key:
            continue
        identity = (parent_key, child_key, relation.relation_type)
        relations_by_identity.setdefault(
            identity,
            SurfaceRelation(
                parent_key=parent_key,
                child_key=child_key,
                relation_type=relation.relation_type,
                confidence=relation.confidence,
                reason=relation.reason,
                source_refs=relation.source_refs,
            ),
        )
    return tuple(relations_by_identity.values())


def _canonical_question_ownership(
    *,
    initial_questions: Sequence[QuestionOwnership],
    canonical_key_by_key: dict[str, str],
) -> tuple[QuestionOwnership, ...]:
    ownership_by_identity: dict[tuple[str, str, QuestionKind], QuestionOwnership] = {}
    for ownership in initial_questions:
        surface_key = canonical_key_by_key.get(
            ownership.surface_key, ownership.surface_key
        )
        identity = (surface_key, ownership.question, ownership.kind)
        ownership_by_identity.setdefault(
            identity,
            QuestionOwnership(
                surface_key=surface_key,
                question=ownership.question,
                kind=ownership.kind,
            ),
        )
    return tuple(ownership_by_identity.values())


def _relation_indexes(
    relations: tuple[SurfaceRelation, ...],
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    parent_keys_by_child: dict[str, set[str]] = {}
    child_keys_by_parent: dict[str, set[str]] = {}
    for relation in relations:
        if relation.relation_type != "umbrella_contains":
            continue
        parent_keys_by_child.setdefault(relation.child_key, set()).add(
            relation.parent_key
        )
        child_keys_by_parent.setdefault(relation.parent_key, set()).add(
            relation.child_key
        )
    return parent_keys_by_child, child_keys_by_parent


def _build_surface_nodes(
    *,
    canonical_candidates: dict[str, SurfaceCandidate],
    parent_keys_by_child: dict[str, set[str]],
    child_keys_by_parent: dict[str, set[str]],
    merged_surfaces: list[MergedSurface],
    question_ownership: tuple[QuestionOwnership, ...],
) -> dict[str, SurfaceNode]:
    absorbed_keys_by_canonical = {
        merged.canonical_key: merged.absorbed_keys for merged in merged_surfaces
    }
    questions_by_surface: dict[str, list[QuestionOwnership]] = {}
    for ownership in question_ownership:
        questions_by_surface.setdefault(ownership.surface_key, []).append(ownership)

    surfaces: dict[str, SurfaceNode] = {}
    for key, candidate in canonical_candidates.items():
        child_keys = tuple(sorted(child_keys_by_parent.get(key, set())))
        parent_keys = tuple(sorted(parent_keys_by_child.get(key, set())))
        surfaces[key] = SurfaceNode(
            key=key,
            title=candidate.title,
            kind=candidate.kind,
            answer_scope=candidate.answer_scope,
            question_scope=candidate.question_scope,
            exclusion_scope=candidate.exclusion_scope,
            answer=_surface_answer(candidate=candidate, child_keys=child_keys),
            parent_keys=parent_keys,
            child_keys=child_keys,
            absorbed_keys=absorbed_keys_by_canonical.get(key, frozenset()),
            source_refs=candidate.source_refs,
            owned_questions=tuple(questions_by_surface.get(key, ())),
        )
    return surfaces


def _surface_answer(*, candidate: SurfaceCandidate, child_keys: tuple[str, ...]) -> str:
    if candidate.answer:
        return candidate.answer
    if candidate.kind == "umbrella" and child_keys:
        children = "; ".join(_display_key(child_key) for child_key in child_keys)
        return (
            f"{candidate.title}: обзорная карточка. Дочерние поверхности: {children}."
        )
    return candidate.answer_scope


def _display_key(surface_key: str) -> str:
    if surface_key.startswith("knowledge_"):
        surface_key = surface_key.removeprefix("knowledge_")
    if surface_key.startswith("surface_"):
        surface_key = surface_key.removeprefix("surface_")
    return surface_key.removesuffix("_merged").replace("_plus_", "+").replace("_", " ")
