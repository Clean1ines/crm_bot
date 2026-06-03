from __future__ import annotations

import re
from dataclasses import dataclass

from .local_claim_search import LocalClaimSearchDocument
from .shared import DomainInvariantError, JsonValue


@dataclass(frozen=True, slots=True)
class LocalClaimSimilaritySignal:
    signal_type: str
    score: float
    matched_values: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.signal_type.strip():
            raise DomainInvariantError("local claim similarity signal type is required")
        if self.score < 0 or self.score > 1:
            raise DomainInvariantError("local claim similarity signal score must be in [0, 1]")


@dataclass(frozen=True, slots=True)
class LocalClaimSimilarityEdge:
    source_search_document_id: str
    target_search_document_id: str
    score: float
    signals: tuple[LocalClaimSimilaritySignal, ...]

    def __post_init__(self) -> None:
        if not self.source_search_document_id.strip():
            raise DomainInvariantError("local claim similarity edge source is required")
        if not self.target_search_document_id.strip():
            raise DomainInvariantError("local claim similarity edge target is required")
        if self.source_search_document_id == self.target_search_document_id:
            raise DomainInvariantError("local claim similarity edge cannot target itself")
        if self.score < 0 or self.score > 1:
            raise DomainInvariantError("local claim similarity edge score must be in [0, 1]")
        if not self.signals:
            raise DomainInvariantError("local claim similarity edge requires signals")


@dataclass(frozen=True, slots=True)
class LocalClaimCandidateGroup:
    group_id: str
    search_document_ids: tuple[str, ...]
    edge_count: int
    max_score: float

    def __post_init__(self) -> None:
        if not self.group_id.strip():
            raise DomainInvariantError("local claim candidate group id is required")
        if not self.search_document_ids:
            raise DomainInvariantError("local claim candidate group requires members")
        if len(set(self.search_document_ids)) != len(self.search_document_ids):
            raise DomainInvariantError("local claim candidate group has duplicate members")
        if self.edge_count < 0:
            raise DomainInvariantError("local claim candidate group edge_count must be non-negative")
        if self.max_score < 0 or self.max_score > 1:
            raise DomainInvariantError("local claim candidate group max_score must be in [0, 1]")


def build_local_claim_similarity_edges(
    documents: tuple[LocalClaimSearchDocument, ...],
    *,
    min_score: float = 0.18,
) -> tuple[LocalClaimSimilarityEdge, ...]:
    if min_score < 0 or min_score > 1:
        raise DomainInvariantError("local claim retrieval min_score must be in [0, 1]")

    edges: list[LocalClaimSimilarityEdge] = []
    ordered_documents = tuple(documents)

    for left_index, left in enumerate(ordered_documents):
        for right in ordered_documents[left_index + 1 :]:
            signals = _similarity_signals(left, right)
            if not signals:
                continue
            score = _edge_score(signals)
            if score < min_score:
                continue
            edges.append(
                LocalClaimSimilarityEdge(
                    source_search_document_id=left.search_document_id,
                    target_search_document_id=right.search_document_id,
                    score=score,
                    signals=signals,
                )
            )

    return tuple(sorted(edges, key=lambda item: (-item.score, item.source_search_document_id, item.target_search_document_id)))


def build_local_claim_candidate_groups(
    documents: tuple[LocalClaimSearchDocument, ...],
    edges: tuple[LocalClaimSimilarityEdge, ...],
) -> tuple[LocalClaimCandidateGroup, ...]:
    document_ids = tuple(document.search_document_id for document in documents)
    document_id_set = set(document_ids)

    adjacency: dict[str, set[str]] = {document_id: set() for document_id in document_ids}
    edge_scores_by_pair: dict[frozenset[str], float] = {}

    for edge in edges:
        if edge.source_search_document_id not in document_id_set:
            raise DomainInvariantError(
                f"unknown local claim similarity edge source: {edge.source_search_document_id}"
            )
        if edge.target_search_document_id not in document_id_set:
            raise DomainInvariantError(
                f"unknown local claim similarity edge target: {edge.target_search_document_id}"
            )
        adjacency[edge.source_search_document_id].add(edge.target_search_document_id)
        adjacency[edge.target_search_document_id].add(edge.source_search_document_id)
        edge_scores_by_pair[frozenset((edge.source_search_document_id, edge.target_search_document_id))] = edge.score

    groups: list[LocalClaimCandidateGroup] = []
    visited: set[str] = set()

    for document_id in document_ids:
        if document_id in visited:
            continue

        stack = [document_id]
        component: list[str] = []
        visited.add(document_id)

        while stack:
            current = stack.pop()
            component.append(current)
            for neighbor in sorted(adjacency[current], reverse=True):
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                stack.append(neighbor)

        ordered_component = tuple(document_id for document_id in document_ids if document_id in set(component))
        component_pairs = {
            pair: score
            for pair, score in edge_scores_by_pair.items()
            if pair.issubset(set(ordered_component))
        }
        max_score = max(component_pairs.values(), default=0.0)

        groups.append(
            LocalClaimCandidateGroup(
                group_id="group:" + "|".join(ordered_component),
                search_document_ids=ordered_component,
                edge_count=len(component_pairs),
                max_score=max_score,
            )
        )

    return tuple(groups)


def _similarity_signals(
    left: LocalClaimSearchDocument,
    right: LocalClaimSearchDocument,
) -> tuple[LocalClaimSimilaritySignal, ...]:
    signals: list[LocalClaimSimilaritySignal] = []

    _append_overlap_signal(
        signals,
        signal_type="claim_text_overlap",
        left_text=left.claim,
        right_text=right.claim,
    )
    _append_sequence_overlap_signal(
        signals,
        signal_type="question_overlap",
        left_values=left.possible_questions,
        right_values=right.possible_questions,
    )
    _append_sequence_overlap_signal(
        signals,
        signal_type="triple_text_overlap",
        left_values=left.triple_texts,
        right_values=right.triple_texts,
    )
    _append_token_set_signal(
        signals,
        signal_type="triple_subject_overlap",
        left_values=_triple_parts(left.triple_texts, index=0),
        right_values=_triple_parts(right.triple_texts, index=0),
    )
    _append_token_set_signal(
        signals,
        signal_type="triple_predicate_overlap",
        left_values=_triple_parts(left.triple_texts, index=1),
        right_values=_triple_parts(right.triple_texts, index=1),
    )
    _append_token_set_signal(
        signals,
        signal_type="triple_object_overlap",
        left_values=_triple_parts(left.triple_texts, index=2),
        right_values=_triple_parts(right.triple_texts, index=2),
    )
    _append_overlap_signal(
        signals,
        signal_type="scope_overlap",
        left_text=left.scope,
        right_text=right.scope,
    )
    _append_overlap_signal(
        signals,
        signal_type="exclusion_scope_overlap",
        left_text=left.exclusion_scope,
        right_text=right.exclusion_scope,
    )
    _append_overlap_signal(
        signals,
        signal_type="evidence_overlap",
        left_text=left.evidence_block,
        right_text=right.evidence_block,
    )
    _append_sequence_overlap_signal(
        signals,
        signal_type="local_relation_signal",
        left_values=left.relation_texts,
        right_values=right.relation_texts,
    )

    return tuple(signal for signal in signals if signal.score > 0)


def _edge_score(signals: tuple[LocalClaimSimilaritySignal, ...]) -> float:
    weights = {
        "claim_text_overlap": 0.24,
        "question_overlap": 0.18,
        "triple_text_overlap": 0.18,
        "triple_subject_overlap": 0.10,
        "triple_predicate_overlap": 0.08,
        "triple_object_overlap": 0.12,
        "scope_overlap": 0.08,
        "exclusion_scope_overlap": 0.04,
        "evidence_overlap": 0.04,
        "local_relation_signal": 0.06,
    }

    weighted_score = 0.0
    total_weight = 0.0
    for signal in signals:
        weight = weights.get(signal.signal_type, 0.0)
        if weight <= 0:
            continue
        weighted_score += signal.score * weight
        total_weight += weight

    if total_weight <= 0:
        return 0.0

    return min(1.0, weighted_score)


def _append_overlap_signal(
    signals: list[LocalClaimSimilaritySignal],
    *,
    signal_type: str,
    left_text: str,
    right_text: str,
) -> None:
    score, matched = _token_overlap(left_text, right_text)
    if score <= 0:
        return
    signals.append(
        LocalClaimSimilaritySignal(
            signal_type=signal_type,
            score=score,
            matched_values=matched,
        )
    )


def _append_sequence_overlap_signal(
    signals: list[LocalClaimSimilaritySignal],
    *,
    signal_type: str,
    left_values: tuple[str, ...],
    right_values: tuple[str, ...],
) -> None:
    score, matched = _sequence_token_overlap(left_values, right_values)
    if score <= 0:
        return
    signals.append(
        LocalClaimSimilaritySignal(
            signal_type=signal_type,
            score=score,
            matched_values=matched,
        )
    )


def _append_token_set_signal(
    signals: list[LocalClaimSimilaritySignal],
    *,
    signal_type: str,
    left_values: tuple[str, ...],
    right_values: tuple[str, ...],
) -> None:
    score, matched = _token_set_overlap(left_values, right_values)
    if score <= 0:
        return
    signals.append(
        LocalClaimSimilaritySignal(
            signal_type=signal_type,
            score=score,
            matched_values=matched,
        )
    )


def _sequence_token_overlap(
    left_values: tuple[str, ...],
    right_values: tuple[str, ...],
) -> tuple[float, tuple[str, ...]]:
    return _token_overlap(" ".join(left_values), " ".join(right_values))


def _token_set_overlap(
    left_values: tuple[str, ...],
    right_values: tuple[str, ...],
) -> tuple[float, tuple[str, ...]]:
    left_tokens = set()
    right_tokens = set()
    for value in left_values:
        left_tokens.update(_tokens(value))
    for value in right_values:
        right_tokens.update(_tokens(value))
    return _jaccard_like_overlap(left_tokens, right_tokens)


def _token_overlap(left_text: str, right_text: str) -> tuple[float, tuple[str, ...]]:
    return _jaccard_like_overlap(_tokens(left_text), _tokens(right_text))


def _jaccard_like_overlap(
    left_tokens: set[str],
    right_tokens: set[str],
) -> tuple[float, tuple[str, ...]]:
    if not left_tokens or not right_tokens:
        return 0.0, ()
    matched = tuple(sorted(left_tokens & right_tokens))
    if not matched:
        return 0.0, ()
    denominator = min(len(left_tokens), len(right_tokens))
    return len(matched) / denominator, matched


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9]+", text.lower())
        if len(token) >= 3
    }


CONTROLLED_TRIPLE_PREDICATES = frozenset(
    {
        "is_a",
        "is_not",
        "has_property",
        "has_capability",
        "has_limitation",
        "requires",
        "supports",
        "uses",
        "produces",
        "includes",
        "has_item",
        "has_step",
        "has_condition",
        "has_result",
        "has_value",
        "has_example",
        "differs_from",
        "excludes",
        "causes",
        "enables",
        "prevents",
        "depends_on",
        "applies_when",
    }
)


def _triple_parts(
    triple_texts: tuple[str, ...],
    *,
    index: int,
) -> tuple[str, ...]:
    result: list[str] = []
    for triple_text in triple_texts:
        subject, predicate, object_ = _parse_triple_text(triple_text)
        parts = (subject, predicate, object_)
        if parts[index].strip():
            result.append(parts[index])
    return tuple(result)


def _parse_triple_text(triple_text: str) -> tuple[str, str, str]:
    tokens = triple_text.split()
    if len(tokens) < 3:
        return triple_text.strip(), "", ""

    for predicate_index, token in enumerate(tokens):
        if token not in CONTROLLED_TRIPLE_PREDICATES:
            continue
        subject = " ".join(tokens[:predicate_index]).strip()
        object_ = " ".join(tokens[predicate_index + 1 :]).strip()
        if subject and object_:
            return subject, token, object_

    subject, predicate, object_ = triple_text.split(" ", 2)
    return subject.strip(), predicate.strip(), object_.strip()


__all__ = [
    "LocalClaimCandidateGroup",
    "LocalClaimSimilarityEdge",
    "LocalClaimSimilaritySignal",
    "build_local_claim_candidate_groups",
    "build_local_claim_similarity_edges",
]
@dataclass(frozen=True, slots=True)
class LocalClaimHybridSearchHit:
    source_search_document_id: str
    target_search_document_id: str
    score: float
    signals: tuple[LocalClaimSimilaritySignal, ...]

    def __post_init__(self) -> None:
        if not self.source_search_document_id.strip():
            raise DomainInvariantError("hybrid search hit source is required")
        if not self.target_search_document_id.strip():
            raise DomainInvariantError("hybrid search hit target is required")
        if self.source_search_document_id == self.target_search_document_id:
            raise DomainInvariantError("hybrid search hit cannot target itself")
        if self.score < 0 or self.score > 1:
            raise DomainInvariantError("hybrid search hit score must be in [0, 1]")
        if not self.signals:
            raise DomainInvariantError("hybrid search hit requires signals")


@dataclass(frozen=True, slots=True)
class LocalClaimHybridSearchTrace:
    document_count: int
    token_posting_count: int
    ngram_posting_count: int
    candidate_pair_count: int
    emitted_edge_count: int
    min_score: float
    candidate_limit_per_document: int

    def __post_init__(self) -> None:
        if self.document_count < 0:
            raise DomainInvariantError("hybrid search trace document_count must be non-negative")
        if self.token_posting_count < 0:
            raise DomainInvariantError("hybrid search trace token_posting_count must be non-negative")
        if self.ngram_posting_count < 0:
            raise DomainInvariantError("hybrid search trace ngram_posting_count must be non-negative")
        if self.candidate_pair_count < 0:
            raise DomainInvariantError("hybrid search trace candidate_pair_count must be non-negative")
        if self.emitted_edge_count < 0:
            raise DomainInvariantError("hybrid search trace emitted_edge_count must be non-negative")
        if self.min_score < 0 or self.min_score > 1:
            raise DomainInvariantError("hybrid search trace min_score must be in [0, 1]")
        if self.candidate_limit_per_document <= 0:
            raise DomainInvariantError("hybrid search trace candidate_limit_per_document must be positive")


def build_local_claim_hybrid_similarity_edges(
    documents: tuple[LocalClaimSearchDocument, ...],
    *,
    min_score: float = 0.18,
    candidate_limit_per_document: int = 80,
) -> tuple[LocalClaimSimilarityEdge, ...]:
    edges, _trace = build_local_claim_hybrid_similarity_edges_with_trace(
        documents,
        min_score=min_score,
        candidate_limit_per_document=candidate_limit_per_document,
    )
    return edges


def build_local_claim_hybrid_similarity_edges_with_trace(
    documents: tuple[LocalClaimSearchDocument, ...],
    *,
    min_score: float = 0.18,
    candidate_limit_per_document: int = 80,
) -> tuple[tuple[LocalClaimSimilarityEdge, ...], LocalClaimHybridSearchTrace]:
    if min_score < 0 or min_score > 1:
        raise DomainInvariantError("local claim hybrid retrieval min_score must be in [0, 1]")
    if candidate_limit_per_document <= 0:
        raise DomainInvariantError("local claim hybrid retrieval candidate_limit_per_document must be positive")

    ordered_documents = tuple(documents)
    if len(ordered_documents) < 2:
        trace = LocalClaimHybridSearchTrace(
            document_count=len(ordered_documents),
            token_posting_count=0,
            ngram_posting_count=0,
            candidate_pair_count=0,
            emitted_edge_count=0,
            min_score=min_score,
            candidate_limit_per_document=candidate_limit_per_document,
        )
        return (), trace

    index = _HybridLocalClaimIndex(ordered_documents)
    pair_best_hits: dict[frozenset[str], LocalClaimHybridSearchHit] = {}
    candidate_pair_count = 0

    for document in ordered_documents:
        hits = search_local_claim_hybrid_candidates(
            document=document,
            index=index,
            min_score=min_score,
            candidate_limit=candidate_limit_per_document,
        )
        candidate_pair_count += len(hits)
        for hit in hits:
            pair_key = frozenset(
                (
                    hit.source_search_document_id,
                    hit.target_search_document_id,
                )
            )
            previous = pair_best_hits.get(pair_key)
            if previous is None or hit.score > previous.score:
                pair_best_hits[pair_key] = hit

    edges = tuple(
        sorted(
            (
                LocalClaimSimilarityEdge(
                    source_search_document_id=tuple(sorted(pair))[0],
                    target_search_document_id=tuple(sorted(pair))[1],
                    score=hit.score,
                    signals=hit.signals,
                )
                for pair, hit in pair_best_hits.items()
            ),
            key=lambda item: (
                -item.score,
                item.source_search_document_id,
                item.target_search_document_id,
            ),
        )
    )

    trace = LocalClaimHybridSearchTrace(
        document_count=len(ordered_documents),
        token_posting_count=len(index.token_postings),
        ngram_posting_count=len(index.ngram_postings),
        candidate_pair_count=candidate_pair_count,
        emitted_edge_count=len(edges),
        min_score=min_score,
        candidate_limit_per_document=candidate_limit_per_document,
    )
    return edges, trace


def search_local_claim_hybrid_candidates(
    *,
    document: LocalClaimSearchDocument,
    index: "_HybridLocalClaimIndex",
    min_score: float = 0.18,
    candidate_limit: int = 80,
) -> tuple[LocalClaimHybridSearchHit, ...]:
    if min_score < 0 or min_score > 1:
        raise DomainInvariantError("local claim hybrid search min_score must be in [0, 1]")
    if candidate_limit <= 0:
        raise DomainInvariantError("local claim hybrid search candidate_limit must be positive")

    candidate_ids = index.candidate_ids_for(document)
    hits: list[LocalClaimHybridSearchHit] = []

    for candidate_id in candidate_ids:
        candidate = index.documents_by_id[candidate_id]
        signals = _hybrid_similarity_signals(document, candidate)
        if not signals:
            continue
        if not _has_strong_cluster_signal(signals):
            continue
        score = _hybrid_edge_score(signals)
        if score < min_score:
            continue
        hits.append(
            LocalClaimHybridSearchHit(
                source_search_document_id=document.search_document_id,
                target_search_document_id=candidate.search_document_id,
                score=score,
                signals=signals,
            )
        )

    return tuple(
        sorted(
            hits,
            key=lambda item: (
                -item.score,
                item.target_search_document_id,
            ),
        )[:candidate_limit]
    )


class _HybridLocalClaimIndex:
    def __init__(self, documents: tuple[LocalClaimSearchDocument, ...]) -> None:
        self.documents = documents
        self.documents_by_id = {
            document.search_document_id: document
            for document in documents
        }
        if len(self.documents_by_id) != len(documents):
            raise DomainInvariantError("hybrid local claim search documents must be unique")

        self.token_postings: dict[str, set[str]] = {}
        self.ngram_postings: dict[str, set[str]] = {}

        for document in documents:
            for token in _hybrid_tokens(document.search_text):
                self.token_postings.setdefault(token, set()).add(document.search_document_id)
            for ngram in _char_ngrams(document.search_text):
                self.ngram_postings.setdefault(ngram, set()).add(document.search_document_id)

    def candidate_ids_for(self, document: LocalClaimSearchDocument) -> tuple[str, ...]:
        candidate_ids: set[str] = set()

        for token in _hybrid_tokens(document.search_text):
            candidate_ids.update(self.token_postings.get(token, set()))

        for ngram in _char_ngrams(document.search_text):
            candidate_ids.update(self.ngram_postings.get(ngram, set()))

        candidate_ids.discard(document.search_document_id)

        return tuple(
            sorted(
                candidate_ids,
                key=lambda candidate_id: (
                    0 if self.documents_by_id[candidate_id].document_id == document.document_id else 1,
                    str(self.documents_by_id[candidate_id].section_id),
                    candidate_id,
                ),
            )
        )


def _hybrid_similarity_signals(
    left: LocalClaimSearchDocument,
    right: LocalClaimSearchDocument,
) -> tuple[LocalClaimSimilaritySignal, ...]:
    signals: list[LocalClaimSimilaritySignal] = list(_similarity_signals(left, right))

    _append_hybrid_token_overlap_signal(
        signals,
        signal_type="search_text_token_overlap",
        left_text=left.search_text,
        right_text=right.search_text,
    )
    _append_char_ngram_signal(
        signals,
        signal_type="search_text_char_ngram_overlap",
        left_text=left.search_text,
        right_text=right.search_text,
    )
    _append_char_ngram_signal(
        signals,
        signal_type="claim_char_ngram_overlap",
        left_text=left.claim,
        right_text=right.claim,
    )
    _append_controlled_predicate_signal(signals, left=left, right=right)

    return tuple(
        sorted(
            _merge_signals(tuple(signal for signal in signals if signal.score > 0)),
            key=lambda item: (-item.score, item.signal_type, item.matched_values),
        )
    )


def _merge_signals(
    signals: tuple[LocalClaimSimilaritySignal, ...],
) -> tuple[LocalClaimSimilaritySignal, ...]:
    best_by_type: dict[str, LocalClaimSimilaritySignal] = {}
    for signal in signals:
        previous = best_by_type.get(signal.signal_type)
        if previous is None or signal.score > previous.score:
            best_by_type[signal.signal_type] = signal
    return tuple(best_by_type.values())


def _has_strong_cluster_signal(
    signals: tuple[LocalClaimSimilaritySignal, ...],
) -> bool:
    strong_thresholds = {
        "triple_text_overlap": 0.34,
        "triple_subject_overlap": 0.50,
        "triple_predicate_overlap": 0.50,
        "controlled_predicate_overlap": 0.50,
        "triple_object_overlap": 0.50,
        "question_overlap": 0.30,
        "scope_overlap": 0.50,
        "evidence_overlap": 0.50,
        "claim_text_overlap": 0.24,
    }

    for signal in signals:
        threshold = strong_thresholds.get(signal.signal_type)
        if threshold is not None and signal.score >= threshold:
            return True

    return False


def _append_hybrid_token_overlap_signal(
    signals: list[LocalClaimSimilaritySignal],
    *,
    signal_type: str,
    left_text: str,
    right_text: str,
) -> None:
    score, matched = _jaccard_like_overlap(
        _hybrid_tokens(left_text),
        _hybrid_tokens(right_text),
    )
    if score <= 0:
        return
    signals.append(
        LocalClaimSimilaritySignal(
            signal_type=signal_type,
            score=score,
            matched_values=matched,
        )
    )


def _hybrid_edge_score(signals: tuple[LocalClaimSimilaritySignal, ...]) -> float:
    weights = {
        "claim_text_overlap": 0.18,
        "claim_char_ngram_overlap": 0.10,
        "search_text_token_overlap": 0.16,
        "search_text_char_ngram_overlap": 0.10,
        "question_overlap": 0.14,
        "triple_text_overlap": 0.12,
        "triple_subject_overlap": 0.08,
        "triple_predicate_overlap": 0.06,
        "controlled_predicate_overlap": 0.08,
        "triple_object_overlap": 0.10,
        "scope_overlap": 0.05,
        "exclusion_scope_overlap": 0.03,
        "evidence_overlap": 0.04,
        "local_relation_signal": 0.06,
    }

    weighted_score = 0.0
    total_weight = 0.0
    for signal in signals:
        weight = weights.get(signal.signal_type, 0.0)
        if weight <= 0:
            continue
        weighted_score += signal.score * weight
        total_weight += weight

    if total_weight <= 0:
        return 0.0

    return min(1.0, weighted_score / total_weight)


def _append_char_ngram_signal(
    signals: list[LocalClaimSimilaritySignal],
    *,
    signal_type: str,
    left_text: str,
    right_text: str,
) -> None:
    score, matched = _char_ngram_overlap(left_text, right_text)
    if score <= 0:
        return
    signals.append(
        LocalClaimSimilaritySignal(
            signal_type=signal_type,
            score=score,
            matched_values=matched,
        )
    )


def _append_controlled_predicate_signal(
    signals: list[LocalClaimSimilaritySignal],
    *,
    left: LocalClaimSearchDocument,
    right: LocalClaimSearchDocument,
) -> None:
    left_predicates = {
        value
        for value in _triple_parts(left.triple_texts, index=1)
        if value in CONTROLLED_TRIPLE_PREDICATES
    }
    right_predicates = {
        value
        for value in _triple_parts(right.triple_texts, index=1)
        if value in CONTROLLED_TRIPLE_PREDICATES
    }
    score, matched = _jaccard_like_overlap(left_predicates, right_predicates)
    if score <= 0:
        return
    signals.append(
        LocalClaimSimilaritySignal(
            signal_type="controlled_predicate_overlap",
            score=score,
            matched_values=matched,
        )
    )


def _char_ngram_overlap(left_text: str, right_text: str) -> tuple[float, tuple[str, ...]]:
    return _jaccard_like_overlap(_char_ngrams(left_text), _char_ngrams(right_text))


def _char_ngrams(text: str, *, size: int = 4) -> set[str]:
    normalized = " ".join(sorted(_hybrid_tokens(text)))
    compact = normalized.replace(" ", "_")
    if len(compact) < size:
        return {compact} if compact else set()
    return {
        compact[index : index + size]
        for index in range(0, len(compact) - size + 1)
    }


def _hybrid_tokens(text: str) -> set[str]:
    return {
        token
        for token in _tokens(text)
        if token not in _HYBRID_STOP_WORDS
    }


_HYBRID_STOP_WORDS = frozenset(
    {
        "для",
        "или",
        "это",
        "как",
        "что",
        "при",
        "the",
        "and",
        "for",
        "with",
        "from",
        "this",
        "that",
        "claim",
        "scope",
        "evidence",
        "triples",
        "possible",
        "questions",
    }
)


try:
    __all__ = tuple(__all__) + (
        "LocalClaimHybridSearchHit",
        "LocalClaimHybridSearchTrace",
        "build_local_claim_hybrid_similarity_edges",
        "build_local_claim_hybrid_similarity_edges_with_trace",
        "search_local_claim_hybrid_candidates",
    )
except NameError:
    __all__ = (
        "LocalClaimHybridSearchHit",
        "LocalClaimHybridSearchTrace",
        "build_local_claim_hybrid_similarity_edges",
        "build_local_claim_hybrid_similarity_edges_with_trace",
        "search_local_claim_hybrid_candidates",
    )

